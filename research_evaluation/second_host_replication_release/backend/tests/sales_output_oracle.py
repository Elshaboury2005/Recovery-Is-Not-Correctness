"""Independent sales-fixture oracle; no ChaosFlow production imports.

Contract: CSV input -> drop rows with null fields -> amount > 0 -> Parquet.
Only the five-column sales fixtures are supported. Float64 values are compared
exactly, full-row multiplicity is retained, and timestamps are UTC-normalized.
The stopped Spark v1 sink log, when present, defines visibility.
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


def utc_timestamp(value):
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def canonical(row, columns):
    values = []
    for column in columns:
        value = row[column]
        if value is None:
            values.append(None)
        elif column == "amount":
            values.append(float(value).hex())
        elif column in ("timestamp", "sale_date"):
            values.append(utc_timestamp(value))
        else:
            values.append(str(value))
    return tuple(values)


def expected(source):
    rows = Counter()
    count = 0
    with Path(source).open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        assert set(columns) in (
            {"transaction_id", "customer_id", "product_id", "amount", "timestamp"},
            {"transaction_id", "customer_id", "product_id", "amount", "sale_date"},
        ), "Unsupported source schema"
        for row in reader:
            count += 1
            if any(row[c] in ("", None) for c in columns):
                continue
            number = float(row["amount"])
            if not math.isfinite(number) or number <= 0:
                continue
            rows[canonical(row, columns)] += 1
    return columns, rows, count


def verify(source, output_path, namenode="http://namenode:9870", timestamp_type="string"):
    root = urlsplit(output_path).path.rstrip("/")
    def get(path, op):
        response = requests.get(f"{namenode}/webhdfs/v1{quote(path, safe='/')}",
                                params={"op": op, "user.name": "root"}, timeout=120)
        response.raise_for_status()
        return response
    def listing(path):
        return get(path, "LISTSTATUS").json()["FileStatuses"]["FileStatus"]

    columns, wanted, input_count = expected(source)
    directory = listing(root)
    manifest_evidence = []
    if any(item["pathSuffix"] == "_spark_metadata" for item in directory):
        metadata = root + "/_spark_metadata"
        names = [i["pathSuffix"] for i in listing(metadata)]
        batches = {int(n.split(".")[0]): n for n in sorted(names)
                   if n.isdigit() or (n.endswith(".compact") and n[:-8].isdigit())}
        snapshots = [b for b, n in batches.items() if n.endswith(".compact")]
        begin = max(snapshots) if snapshots else 0
        if not batches:
            raise ValueError("No committed sink metadata")
        visible = set()
        for batch in range(begin, max(batches) + 1):
            log_path = f"{metadata}/{batches[batch]}"  # Missing batches fail closed.
            data = get(log_path, "OPEN").content
            lines = data.decode().splitlines()
            if not lines or lines[0] != "v1":
                raise ValueError("Unknown/truncated sink log")
            manifest_evidence.append({"path": log_path, "sha256": hashlib.sha256(data).hexdigest()})
            for line in lines[1:]:
                item = json.loads(line)
                remote = unquote(urlsplit(item["path"]).path)
                if item["action"] != "add" or item["isDir"] or not remote.startswith(root + "/"):
                    raise ValueError("Unsupported commit entry")
                visible.add(remote)
        files = sorted(visible)
    else:
        files = sorted(f"{root}/{i['pathSuffix']}" for i in directory
                       if i["type"] == "FILE" and i["pathSuffix"].startswith("part-") and i["pathSuffix"].endswith(".parquet"))
        if not files:
            raise ValueError("No output Parquet files")

    observed = Counter()
    evidence = []
    schema_ok = True
    invariant_errors = 0
    schemas = []
    for remote in files:
        data = get(remote, "OPEN").content
        parquet = pq.ParquetFile(BytesIO(data))
        # Spark may commit a schema-only part with zero row groups. PyArrow
        # 18's read() can ask for group -1 on these files; footer/schema are
        # still valid and explicitly establish zero rows, unlike missing data.
        if parquet.metadata.num_row_groups == 0 and parquet.metadata.num_rows == 0:
            table = pa.Table.from_batches([], schema=parquet.schema_arrow)
        else:
            table = parquet.read(use_threads=False)
        schema_valid = table.column_names == columns
        for field in table.schema:
            if field.name == "amount":
                schema_valid &= pa.types.is_float64(field.type)
            elif field.name in ("timestamp", "sale_date") and timestamp_type == "timestamp":
                schema_valid &= pa.types.is_timestamp(field.type)
            elif field.name in ("timestamp", "sale_date") and timestamp_type == "date":
                schema_valid &= pa.types.is_date32(field.type)
            else:
                schema_valid &= pa.types.is_string(field.type)
        schema_ok &= schema_valid
        schemas.append(str(table.schema))
        for row in table.to_pylist():
            if any(row.get(c) is None for c in columns):
                invariant_errors += 1
            amount = row.get("amount")
            if amount is not None and (not math.isfinite(float(amount)) or float(amount) <= 0):
                invariant_errors += 1
            observed[canonical(row, columns)] += 1
        evidence.append({"path": remote, "rows": table.num_rows, "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})
    missing, extra = wanted - observed, observed - wanted
    def digest(rows):
        content = sorted((json.dumps(row, separators=(",", ":")), count) for row, count in rows.items())
        return hashlib.sha256(json.dumps(content, separators=(",", ":")).encode()).hexdigest()
    return {
        "oracle_version": "sales-full-multiset-v2-exact-float64", "input_records": input_count,
        "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        "output_path": root, "expected_records": wanted.total(), "actual_records": observed.total(),
        "missing_records": missing.total(), "unexpected_records": extra.total(),
        "schema_valid": schema_ok, "invariant_errors": invariant_errors,
        "output_correct": not missing and not extra and schema_ok and invariant_errors == 0,
        "expected_multiset_sha256": digest(wanted), "actual_multiset_sha256": digest(observed),
        "part_files": evidence, "sink_metadata": manifest_evidence, "schemas": sorted(set(schemas)),
        "verification_scope": "stopped append sink; fixed sales transformations; exact float64",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--timestamp-type", choices=("string", "timestamp", "date"), default="string")
    args = parser.parse_args()
    try:
        report = verify(args.source, args.output_path, timestamp_type=args.timestamp_type)
    except Exception as exc:
        report = {"output_correct": None, "status": "UNKNOWN", "error": str(exc)}
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report.get("output_correct") is True else 1)
