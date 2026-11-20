import csv

import pyarrow as pa
import pyarrow.parquet as pq

from tests.aggregate_output_oracle import verify_parts


def source_file(tmp_path):
    source = tmp_path / "source.csv"
    with source.open("w", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["transaction_id", "customer_id", "product_id", "amount"])
        writer.writerows([["1", "a", "p", "4"], ["1", "a", "p", "4"], ["2", "b", "p", "5"], ["3", "b", "", "9"]])
    return source


def part(rows):
    sink = pa.BufferOutputStream()
    pq.write_table(pa.table({"customer_id": [row[0] for row in rows], "sum_amount": [row[1] for row in rows]},
                            schema=pa.schema([("customer_id", pa.string()), ("sum_amount", pa.float64())])), sink)
    return sink.getvalue().to_pybytes()


def test_w5_independent_oracle_accepts_exact_group_sums(tmp_path):
    result = verify_parts(str(source_file(tmp_path)), [part([("a", 4.0), ("b", 5.0)])])
    assert result["output_correct"] is True and result["post_transform_records"] == 2


def test_w5_independent_oracle_rejects_extra_or_wrong_group(tmp_path):
    result = verify_parts(str(source_file(tmp_path)), [part([("a", 8.0), ("b", 5.0), ("c", 1.0)])])
    assert result["output_correct"] is False
    assert result["mismatched_groups"] == ["a"] and result["unexpected_groups"] == ["c"]
