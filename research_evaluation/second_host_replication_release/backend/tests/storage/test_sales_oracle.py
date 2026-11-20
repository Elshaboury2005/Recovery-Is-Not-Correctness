"""Independent-reader regression fixtures, not naturally observed corruption."""
from datetime import date, datetime
from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tests.sales_output_oracle import canonical, verify


def test_schema_only_parquet_is_valid_empty_output(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("transaction_id,customer_id,product_id,amount,timestamp\nTX,C,P,-1,2024-01-01\n")
    schema = pa.schema([("transaction_id", pa.string()), ("customer_id", pa.string()),
                        ("product_id", pa.string()), ("amount", pa.float64()), ("timestamp", pa.string())])
    sink = pa.BufferOutputStream()
    with pq.ParquetWriter(sink, schema):
        pass  # Valid footer, zero row groups, no rows.
    payload = sink.getvalue().to_pybytes()
    listing = Mock(); listing.json.return_value = {"FileStatuses": {"FileStatus": [
        {"type": "FILE", "pathSuffix": "part-empty.parquet"}]}}
    part = Mock(); part.content = payload
    with patch("tests.sales_output_oracle.requests.get", side_effect=[listing, part]):
        report = verify(source, "/fixture")
    assert report["expected_records"] == report["actual_records"] == 0
    assert report["output_correct"] is True


def test_exact_float_comparison_does_not_round_away_corruption():
    assert canonical({"amount": 1.001}, ["amount"]) != canonical({"amount": 1.0}, ["amount"])


def test_date_and_midnight_timestamp_normalize_equally():
    assert canonical({"sale_date": date(2024, 1, 1)}, ["sale_date"]) == canonical(
        {"sale_date": datetime(2024, 1, 1)}, ["sale_date"])
