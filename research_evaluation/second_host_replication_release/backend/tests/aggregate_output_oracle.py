"""Independent W5 aggregate oracle; it deliberately imports no application code."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
from urllib.parse import quote, urlsplit

import pyarrow as pa
import pyarrow.parquet as pq
import requests

EXPECTED_SCHEMA = pa.schema([("customer_id", pa.string()), ("sum_amount", pa.float64())])


def expected(source: str) -> tuple[dict[str, float], dict]:
    totals: dict[str, int] = defaultdict(int)
    seen: set[tuple[str | None, ...]] = set()
    inputs = kept = 0
    with Path(source).open(newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["transaction_id", "customer_id", "product_id", "amount"]
        for raw in reader:
            inputs += 1
            row = tuple(raw[name] if raw[name] != "" else None for name in reader.fieldnames)
            if any(item is None for item in row) or row in seen:
                continue
            seen.add(row)
            value = float(raw["amount"])
            assert math.isfinite(value) and value.is_integer()
            if value > 0:
                totals[raw["customer_id"]] += int(value); kept += 1
    return {key: float(value) for key, value in totals.items()}, {"input_records": inputs, "post_transform_records": kept}


def verify_parts(source: str, parts: list[bytes]) -> dict:
    wanted, evidence = expected(source)
    observed: dict[str, float] = {}
    duplicate_groups = invalid = 0
    part_evidence = []
    for number, content in enumerate(parts):
        data = pq.ParquetFile(BytesIO(content))
        schema_valid = data.schema_arrow == EXPECTED_SCHEMA
        if not schema_valid:
            invalid += 1
            continue
        table = data.read(use_threads=False)
        for row in table.to_pylist():
            group, value = row["customer_id"], row["sum_amount"]
            if group is None or value is None or not math.isfinite(float(value)):
                invalid += 1; continue
            if group in observed:
                duplicate_groups += 1
            observed[group] = float(value)
        part_evidence.append({"part": number, "rows": table.num_rows, "sha256": hashlib.sha256(content).hexdigest()})
    missing = sorted(set(wanted) - set(observed))
    unexpected = sorted(set(observed) - set(wanted))
    mismatched = sorted(key for key in set(wanted) & set(observed) if wanted[key] != observed[key])
    correct = not missing and not unexpected and not mismatched and not duplicate_groups and not invalid
    return {"oracle_version": "w5-batch-aggregate-independent-v1", "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            **evidence, "expected_groups": len(wanted), "actual_groups": len(observed),
            "missing_groups": missing, "unexpected_groups": unexpected, "mismatched_groups": mismatched,
            "duplicate_groups": duplicate_groups, "invariant_errors": invalid, "part_files": part_evidence,
            "output_correct": correct, "verification_scope": "finite CSV full-row-dedup positive integer grouped sum"}


def verify(source: str, output_path: str, namenode: str = "http://namenode:9870") -> dict:
    root = urlsplit(output_path).path.rstrip("/")
    def get(path: str, op: str):
        reply = requests.get(f"{namenode}/webhdfs/v1{quote(path, safe='/')}", params={"op": op, "user.name": "root"}, timeout=120)
        reply.raise_for_status(); return reply
    entries = get(root, "LISTSTATUS").json()["FileStatuses"]["FileStatus"]
    files = sorted(f"{root}/{entry['pathSuffix']}" for entry in entries
                   if entry["type"] == "FILE" and entry["pathSuffix"].startswith("part-") and entry["pathSuffix"].endswith(".parquet"))
    if not files:
        raise ValueError("No committed batch Parquet part files")
    return verify_parts(source, [get(name, "OPEN").content for name in files])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source", required=True); parser.add_argument("--output-path", required=True)
    values = parser.parse_args()
    try:
        report = verify(values.source, values.output_path)
    except Exception as exc:
        report = {"output_correct": None, "status": "UNKNOWN", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report.get("output_correct") is True else 1)
