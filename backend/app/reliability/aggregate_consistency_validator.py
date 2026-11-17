"""Bounded exact contract for the Phase 2 W5 batch aggregation pilot.

This is deliberately narrower than a general SQL reference engine.  It checks
the declared CSV -> remove-null -> full-row-dedup -> positive-amount-filter ->
grouped integer-valued sum contract.  Integral input amounts keep the expected
sum exact across a distributed floating-point reduction.  Unsupported
configuration or incomplete evidence is UNKNOWN, never a passing result.
"""
from __future__ import annotations

import csv
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time

import pyarrow as pa
import pyarrow.parquet as pq


class ContractUnavailable(ValueError):
    """The bounded W5 contract cannot establish a verdict."""


EXPECTED_SCHEMA = pa.schema([("customer_id", pa.string()), ("sum_amount", pa.float64())])


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _unknown(reason: str, **evidence):
    return {
        "validator_version": "w5-batch-aggregate-exact-v1",
        "validation_status": "UNKNOWN", "validation_passed": None,
        "output_correct": None, "reason": reason,
        "expected_groups": None, "actual_groups": None,
        "missing_groups": None, "unexpected_groups": None,
        "mismatched_groups": None, **evidence,
    }


def _check_config(config: dict) -> tuple[str, str, str]:
    if config.get("source", {}).get("type") != "csv" or config.get("streaming", {}).get("enabled"):
        raise ContractUnavailable("Only finite batch CSV aggregation is supported")
    names = [field.get("name") for field in config.get("schema", [])]
    types = {field.get("name"): field.get("type") for field in config.get("schema", [])}
    operations = config.get("processing", {}).get("operations", [])
    required = ["remove_nulls", "remove_duplicates", "filter", "aggregate"]
    if [operation.get("type") for operation in operations] != required:
        raise ContractUnavailable("W5 requires remove_nulls, remove_duplicates, filter, aggregate in that order")
    filt, aggregate = operations[2], operations[3]
    if filt.get("condition", "").replace(" ", "") != "amount>0":
        raise ContractUnavailable("W5 requires the exact amount > 0 filter")
    group, field = aggregate.get("group_by"), aggregate.get("field")
    if aggregate.get("operation") != "sum" or group not in names or field not in names:
        raise ContractUnavailable("W5 requires a declared grouped sum")
    if types.get(group) != "string" or types.get(field) != "double":
        raise ContractUnavailable("W5 requires string group and double summed field")
    return group, field, str(config["source"].get("path", ""))


def _expected(source: Path, group: str, field: str, max_rows: int) -> tuple[dict[str, float], dict]:
    totals: dict[str, int] = defaultdict(int)
    seen: set[tuple[str | None, ...]] = set()
    input_records = retained_records = 0
    with source.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or group not in reader.fieldnames or field not in reader.fieldnames:
            raise ContractUnavailable("CSV header differs from declared aggregate fields")
        for raw in reader:
            input_records += 1
            if input_records > max_rows:
                raise ContractUnavailable("Source row bound exceeded")
            row = tuple(raw[name] if raw[name] != "" else None for name in reader.fieldnames)
            if any(value is None for value in row):
                continue
            if row in seen:
                continue
            seen.add(row)
            try:
                value = float(raw[field])
            except ValueError as exc:
                raise ContractUnavailable("Non-numeric aggregate value") from exc
            if not math.isfinite(value) or not value.is_integer() or abs(value) > 1_000_000_000:
                raise ContractUnavailable("W5 requires finite integer-valued amounts within bound")
            if value <= 0:
                continue
            totals[str(raw[group])] += int(value)
            retained_records += 1
    return {key: float(value) for key, value in totals.items()}, {
        "input_records": input_records, "post_transform_records": retained_records,
        "expected_sum_total": float(sum(totals.values())),
    }


class AggregateConsistencyValidator:
    """Validate the narrow W5 aggregate output after its writer has stopped."""

    def validate(self, *, output_location: dict | None, pipeline_config: dict | None,
                 writer_stopped: bool, expected_source_sha256: str | None = None,
                 max_rows: int = 100_000, max_source_bytes: int = 64 * 1024 * 1024,
                 max_output_bytes: int = 256 * 1024 * 1024, max_seconds: int = 180) -> dict:
        start = time.monotonic()
        evidence = {"validation_scope": "W5 finite batch exact grouped integer sum",
                    "limits": {"max_rows": max_rows, "max_source_bytes": max_source_bytes,
                               "max_output_bytes": max_output_bytes, "max_seconds": max_seconds}}
        try:
            if not writer_stopped or not pipeline_config or not output_location:
                raise ContractUnavailable("Stopped writer, configuration, and exact output location are required")
            if hasattr(pipeline_config, "model_dump"):
                pipeline_config = pipeline_config.model_dump(by_alias=True)
            evidence["configuration_sha256"] = hashlib.sha256(
                json.dumps(pipeline_config, sort_keys=True).encode()).hexdigest()
            group, field, source_name = _check_config(pipeline_config)
            source = Path(source_name)
            if not source.is_file() or source.stat().st_size > max_source_bytes:
                raise ContractUnavailable("Source missing or exceeds bound")
            source_sha256 = _sha256(source)
            evidence["source_sha256"] = source_sha256
            if expected_source_sha256 and source_sha256 != expected_source_sha256:
                raise ContractUnavailable("Source identity differs from captured source")
            expected, source_evidence = _expected(source, group, field, max_rows)
            evidence.update(source_evidence)
            observed: dict[str, float] = {}
            duplicate_groups = nonfinite_values = 0
            total_bytes = 0
            parts = []
            for remote, local, size in self._output_files(output_location):
                total_bytes += size
                if total_bytes > max_output_bytes:
                    raise ContractUnavailable("Output byte bound exceeded")
                path = local() if callable(local) else local
                parquet = pq.ParquetFile(path)
                schema_valid = parquet.schema_arrow == EXPECTED_SCHEMA
                if not schema_valid:
                    raise ContractUnavailable("Aggregate output schema differs from customer_id:string,sum_amount:double")
                table = parquet.read(use_threads=False)
                for row in table.to_pylist():
                    key, value = row["customer_id"], row["sum_amount"]
                    if key is None or value is None or not math.isfinite(float(value)):
                        nonfinite_values += 1
                        continue
                    if key in observed:
                        duplicate_groups += 1
                    observed[key] = float(value)
                parts.append({"path": remote, "rows": table.num_rows, "bytes": size, "sha256": _sha256(Path(path))})
                if time.monotonic() - start > max_seconds:
                    raise ContractUnavailable("Validation computation deadline exceeded")
            if not parts:
                raise ContractUnavailable("No committed Parquet output parts")
            missing = sorted(set(expected) - set(observed))
            unexpected = sorted(set(observed) - set(expected))
            mismatched = sorted(key for key in set(expected) & set(observed) if expected[key] != observed[key])
            passed = not missing and not unexpected and not mismatched and not duplicate_groups and not nonfinite_values
            return {**_unknown("", **evidence), "validation_status": "PASS" if passed else "FAIL",
                    "validation_passed": passed, "output_correct": passed, "reason": None,
                    "expected_groups": len(expected), "actual_groups": len(observed),
                    "missing_groups": missing, "unexpected_groups": unexpected,
                    "mismatched_groups": mismatched, "duplicate_groups": duplicate_groups,
                    "invariant_errors": nonfinite_values, "parts": parts,
                    "validation_seconds": time.monotonic() - start}
        except Exception as exc:
            return _unknown(f"{type(exc).__name__}: {exc}", **evidence,
                            validation_seconds=time.monotonic() - start)

    @staticmethod
    def _output_files(output_location: dict):
        path, storage = output_location.get("path"), output_location.get("storage_type")
        if not path:
            raise ContractUnavailable("Missing exact output path")
        if storage == "local":
            root = Path(path)
            files = sorted(root.glob("*.parquet")) if root.is_dir() else [root]
            for part in files:
                if part.is_file():
                    yield str(part), part, part.stat().st_size
            return
        if storage != "hdfs":
            raise ContractUnavailable(f"Unsupported storage: {storage}")
        from app.storage.hdfs_client import HdfsStorageClient
        client = HdfsStorageClient()
        for number, remote in enumerate(client.parquet_paths(path)):
            size = client._hdfs_client.status(remote)["length"]
            local = Path(tempfile.mkdtemp(prefix="w5-aggregate-")) / f"part-{number}.parquet"
            def download(remote=remote, local=local):
                client._hdfs_client.download(remote, str(local))
                return local
            yield remote, download, size
