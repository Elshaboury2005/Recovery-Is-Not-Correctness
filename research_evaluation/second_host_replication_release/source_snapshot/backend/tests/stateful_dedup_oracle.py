"""Independent finite W4 oracle; it imports no ChaosFlow production modules.

Supported scope is deliberately narrow: CSV with five named columns, ordered
``remove_nulls -> full-row remove_duplicates -> amount > 0``, and a stopped
Spark append sink with a readable v1 commit log.  It is independent from the
production Arrow/SQLite validator and Spark transformation implementation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import pyarrow as pa
import pyarrow.parquet as pq
import requests


COLUMNS = ["transaction_id", "customer_id", "product_id", "amount", "event_time"]


def schema_compatible(schema) -> bool:
    expected = [pa.string(), pa.string(), pa.string(), pa.float64(), pa.timestamp("us")]
    if schema.names != COLUMNS:
        return False
    for observed, wanted in zip(schema, expected):
        if pa.types.is_timestamp(wanted):
            if not pa.types.is_timestamp(observed.type) or observed.type.tz is not None:
                return False
        elif observed.type != wanted:
            return False
    return True


def submicrosecond_timestamp_values(table) -> int:
    column = table.column("event_time")
    if column.type.unit != "ns":
        return 0
    return sum(value is not None and value % 1_000 != 0
               for value in column.cast(pa.int64()).to_pylist())


def utc_timestamp(value) -> str:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(timespec="microseconds")


def canonical(row) -> tuple:
    return (
        str(row["transaction_id"]),
        str(row["customer_id"]),
        str(row["product_id"]),
        float(row["amount"]).hex(),
        utc_timestamp(row["event_time"]),
    )


def expected(source: str | Path) -> tuple[Counter, int]:
    wanted: Counter = Counter()
    seen = set()
    inputs = 0
    with Path(source).open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"Unsupported W4 source schema: {reader.fieldnames!r}")
        for row in reader:
            inputs += 1
            if any(row[column] in ("", None) for column in COLUMNS):
                continue
            current = canonical(row)
            if current in seen:
                continue
            seen.add(current)
            amount = float(row["amount"])
            if not math.isfinite(amount) or amount <= 0:
                continue
            wanted[current] += 1
    return wanted, inputs


def _digest(rows: Counter) -> str:
    value = sorted((json.dumps(row, separators=(",", ":")), count) for row, count in rows.items())
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def verify(source: str | Path, output_path: str, namenode: str = "http://namenode:9870") -> dict:
    root = urlsplit(output_path).path.rstrip("/")

    def get(path: str, operation: str):
        response = requests.get(
            f"{namenode}/webhdfs/v1{quote(path, safe='/')}",
            params={"op": operation, "user.name": "root"},
            timeout=120,
        )
        response.raise_for_status()
        return response

    def listing(path: str):
        return get(path, "LISTSTATUS").json()["FileStatuses"]["FileStatus"]

    wanted, input_records = expected(source)
    directory = listing(root)
    if not any(item["pathSuffix"] == "_spark_metadata" for item in directory):
        raise ValueError("Stopped streaming sink has no _spark_metadata directory")
    metadata = root + "/_spark_metadata"
    names = [item["pathSuffix"] for item in listing(metadata)]
    batches = {int(name.split(".")[0]): name for name in names
               if name.isdigit() or (name.endswith(".compact") and name[:-8].isdigit())}
    if not batches:
        raise ValueError("No committed sink metadata")
    compact = [batch for batch, name in batches.items() if name.endswith(".compact")]
    begin = max(compact) if compact else 0
    if any(batch not in batches for batch in range(begin, max(batches) + 1)):
        raise ValueError("Sink commit log has a gap")
    committed: set[str] = set()
    metadata_evidence = []
    for batch in range(begin, max(batches) + 1):
        remote = f"{metadata}/{batches[batch]}"
        payload = get(remote, "OPEN").content
        lines = payload.decode().splitlines()
        if not lines or lines[0] != "v1":
            raise ValueError("Unsupported or truncated sink log")
        metadata_evidence.append({"path": remote, "sha256": hashlib.sha256(payload).hexdigest()})
        for line in lines[1:]:
            item = json.loads(line)
            path = unquote(urlsplit(item["path"]).path)
            if item.get("action") != "add" or item.get("isDir") or not path.startswith(root + "/"):
                raise ValueError("Unsupported sink commit entry")
            committed.add(path)
    observed: Counter = Counter()
    parts = []
    schema_valid = True
    invariant_errors = 0
    for remote in sorted(committed):
        payload = get(remote, "OPEN").content
        part = pq.ParquetFile(BytesIO(payload))
        if part.metadata.num_row_groups == 0 and part.metadata.num_rows == 0:
            table = pa.Table.from_batches([], schema=part.schema_arrow)
        else:
            table = part.read(use_threads=False)
        schema_valid &= schema_compatible(table.schema)
        invariant_errors += submicrosecond_timestamp_values(table)
        for row in table.to_pylist():
            observed[canonical(row)] += 1
        parts.append({"path": remote, "rows": table.num_rows, "bytes": len(payload),
                      "sha256": hashlib.sha256(payload).hexdigest()})
    missing, extra = wanted - observed, observed - wanted
    correct = not missing and not extra and schema_valid and invariant_errors == 0
    return {
        "oracle_version": "stateful-dedup-full-row-v1",
        "verification_scope": "finite one-event-time streaming deduplication; stopped Spark append sink; exact row multiset",
        "input_records": input_records,
        "expected_records": wanted.total(),
        "actual_records": observed.total(),
        "missing_records": missing.total(),
        "unexpected_records": extra.total(),
        "schema_valid": schema_valid,
        "invariant_errors": invariant_errors,
        "output_correct": correct,
        "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        "output_path": root,
        "expected_multiset_sha256": _digest(wanted),
        "actual_multiset_sha256": _digest(observed),
        "part_files": parts,
        "sink_metadata": metadata_evidence,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()
    try:
        result = verify(args.source, args.output_path)
    except Exception as exc:
        result = {"status": "UNKNOWN", "output_correct": None, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get("output_correct") is True else 1)
