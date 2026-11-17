import csv
import hashlib

import pyarrow as pa
import pyarrow.parquet as pq

from app.reliability.aggregate_consistency_validator import AggregateConsistencyValidator


def config(source):
    return {"source": {"type": "csv", "path": str(source)},
            "schema": [{"name": "transaction_id", "type": "string"}, {"name": "customer_id", "type": "string"},
                       {"name": "product_id", "type": "string"}, {"name": "amount", "type": "double"}],
            "processing": {"operations": [{"type": "remove_nulls"}, {"type": "remove_duplicates"},
                         {"type": "filter", "condition": "amount > 0"},
                         {"type": "aggregate", "group_by": "customer_id", "operation": "sum", "field": "amount"}]},
            "streaming": {"enabled": False}}


def source_file(tmp_path):
    source = tmp_path / "input.csv"
    with source.open("w", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["transaction_id", "customer_id", "product_id", "amount"])
        writer.writerows([["1", "c1", "p1", "10"], ["1", "c1", "p1", "10"], ["2", "c1", "p2", "-2"],
                          ["3", "c2", "p3", "7"], ["4", "c2", "", "3"]])
    return source


def output(tmp_path, rows):
    root = tmp_path / "out"; root.mkdir()
    pq.write_table(pa.table({"customer_id": [r[0] for r in rows], "sum_amount": [r[1] for r in rows]},
                            schema=pa.schema([("customer_id", pa.string()), ("sum_amount", pa.float64())])), root / "part-0.parquet")
    return root


def validate(source, root):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return AggregateConsistencyValidator().validate(output_location={"storage_type": "local", "path": str(root)},
        pipeline_config=config(source), writer_stopped=True, expected_source_sha256=digest)


def test_w5_exact_aggregate_passes_with_full_row_dedup_and_filter(tmp_path):
    result = validate(source_file(tmp_path), output(tmp_path, [("c1", 10.0), ("c2", 7.0)]))
    assert result["validation_status"] == "PASS"
    assert result["input_records"] == 5 and result["post_transform_records"] == 2


def test_w5_exact_aggregate_rejects_wrong_sum(tmp_path):
    result = validate(source_file(tmp_path), output(tmp_path, [("c1", 20.0), ("c2", 7.0)]))
    assert result["validation_status"] == "FAIL"
    assert result["mismatched_groups"] == ["c1"]


def test_w5_contract_rejects_nonintegral_input(tmp_path):
    source = source_file(tmp_path)
    with source.open("a") as stream:
        stream.write("5,c3,p4,1.5\n")
    result = validate(source, output(tmp_path, [("c1", 10.0), ("c2", 7.0), ("c3", 1.5)]))
    assert result["validation_status"] == "UNKNOWN"
    assert "integer-valued" in result["reason"]
