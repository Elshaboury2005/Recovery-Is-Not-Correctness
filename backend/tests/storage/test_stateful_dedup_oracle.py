"""Unit checks for the W4 independent oracle, using controlled local fixtures."""
from datetime import datetime
from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.parquet as pq

from tests.stateful_dedup_oracle import expected, verify


def test_expected_keeps_one_positive_full_row_after_ordered_operations(tmp_path):
    source = tmp_path / "events.csv"
    source.write_text(
        "transaction_id,customer_id,product_id,amount,event_time\n"
        "T1,C1,P1,1.25,2026-01-01T00:00:00Z\n"
        "T1,C1,P1,1.25,2026-01-01T00:00:00Z\n"
        "T2,C2,P2,-1,2026-01-01T00:00:00Z\n"
        "T2,C2,P2,-1,2026-01-01T00:00:00Z\n"
        "T3,C3,P3,,2026-01-01T00:00:00Z\n"
    )
    rows, input_records = expected(source)
    assert input_records == 5
    assert rows.total() == 1


def test_stopped_sink_oracle_accepts_microsecond_aligned_spark_timestamp_output(tmp_path):
    source = tmp_path / "events.csv"
    source.write_text(
        "transaction_id,customer_id,product_id,amount,event_time\n"
        "T1,C1,P1,1.25,2026-01-01T00:00:00Z\n"
        "T1,C1,P1,1.25,2026-01-01T00:00:00Z\n"
    )
    schema = pa.schema([
        ("transaction_id", pa.string()), ("customer_id", pa.string()),
        ("product_id", pa.string()), ("amount", pa.float64()),
        ("event_time", pa.timestamp("ns")),
    ])
    sink = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist([{
        "transaction_id": "T1", "customer_id": "C1", "product_id": "P1", "amount": 1.25,
        "event_time": datetime(2026, 1, 1),
    }], schema=schema), sink)
    listing_root = Mock(); listing_root.json.return_value = {"FileStatuses": {"FileStatus": [{"pathSuffix": "_spark_metadata"}]}}
    listing_metadata = Mock(); listing_metadata.json.return_value = {"FileStatuses": {"FileStatus": [{"pathSuffix": "0"}]}}
    log = Mock(); log.content = b'v1\n{"action":"add","path":"hdfs://namenode:9000/fixture/part-0.parquet","isDir":false}\n'
    part = Mock(); part.content = sink.getvalue().to_pybytes()
    with patch("tests.stateful_dedup_oracle.requests.get", side_effect=[listing_root, listing_metadata, log, part]):
        result = verify(source, "/fixture")
    assert result["output_correct"] is True
    assert result["expected_records"] == result["actual_records"] == 1


def test_stopped_sink_oracle_rejects_submicrosecond_timestamp_value(tmp_path):
    source = tmp_path / "events.csv"
    source.write_text(
        "transaction_id,customer_id,product_id,amount,event_time\n"
        "T1,C1,P1,1.25,2026-01-01T00:00:00Z\n"
    )
    schema = pa.schema([
        ("transaction_id", pa.string()), ("customer_id", pa.string()),
        ("product_id", pa.string()), ("amount", pa.float64()),
        ("event_time", pa.timestamp("ns")),
    ])
    sink = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_arrays([
        pa.array(["T1"]), pa.array(["C1"]), pa.array(["P1"]), pa.array([1.25]),
        pa.array([1767225600000000001], type=pa.timestamp("ns")),
    ], schema=schema), sink)
    listing_root = Mock(); listing_root.json.return_value = {"FileStatuses": {"FileStatus": [{"pathSuffix": "_spark_metadata"}]}}
    listing_metadata = Mock(); listing_metadata.json.return_value = {"FileStatuses": {"FileStatus": [{"pathSuffix": "0"}]}}
    log = Mock(); log.content = b'v1\n{"action":"add","path":"hdfs://namenode:9000/fixture/part-0.parquet","isDir":false}\n'
    part = Mock(); part.content = sink.getvalue().to_pybytes()
    with patch("tests.stateful_dedup_oracle.requests.get", side_effect=[listing_root, listing_metadata, log, part]):
        result = verify(source, "/fixture")
    assert result["output_correct"] is False
    assert result["invariant_errors"] == 1
