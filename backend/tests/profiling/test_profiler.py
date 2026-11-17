from __future__ import annotations

import json

import pandas as pd
import pytest

from app.profiling.profiler import DatasetProfileError, DatasetProfiler


def test_csv_profile_uses_exact_record_count_and_reports_sample_scope(tmp_path) -> None:
    path = tmp_path / "events.csv"
    pd.DataFrame(
        {
            "event_id": ["a", "b", "b", "c"],
            "amount": [1.0, 2.0, 2.0, None],
            "event_time": ["2026-01-01T00:00:00Z"] * 4,
        }
    ).to_csv(path, index=False)
    result = DatasetProfiler().profile(str(path), sample_rows=2)
    assert result["record_count"] == {"value": 4, "scope": "exact"}
    assert result["dataset"]["format"] == "csv"
    assert result["statistics_scope"]["columns"] == "sampled"
    assert "event_time" in result["timestamp_fields"]
    assert result["duplicate_characteristics"]["duplicate_rows"] == 0


def test_numeric_amount_is_not_misclassified_as_timestamp(tmp_path) -> None:
    path = tmp_path / "sales.csv"
    pd.DataFrame(
        {
            "amount": [10.5, 20.0],
            "sale_date": ["2026-01-01", "2026-01-02"],
        }
    ).to_csv(path, index=False)

    result = DatasetProfiler().profile(str(path))

    assert result["timestamp_fields"] == ["sale_date"]


def test_json_array_profile_is_bounded_and_exact_for_small_input(tmp_path) -> None:
    path = tmp_path / "events.json"
    path.write_text(json.dumps([{"id": 1}, {"id": 2}, {"id": 2}]), encoding="utf-8")
    result = DatasetProfiler().profile(str(path), sample_rows=100)
    assert result["record_count"]["value"] == 3
    assert result["record_count"]["scope"] == "exact"
    assert result["duplicate_characteristics"]["duplicate_rows"] == 1


def test_parquet_profile_counts_row_groups_without_loading_full_file(tmp_path) -> None:
    path = tmp_path / "events.parquet"
    pd.DataFrame({"id": range(20), "value": [float(x) for x in range(20)]}).to_parquet(path, index=False)
    result = DatasetProfiler().profile(str(path), sample_rows=5)
    assert result["record_count"] == {"value": 20, "scope": "exact"}
    assert result["partition_characteristics"]["row_group_count"] >= 1
    assert result["statistics_scope"]["numeric_distributions"] == "sampled"


def test_large_json_array_is_rejected_instead_of_loaded(tmp_path) -> None:
    path = tmp_path / "large.json"
    path.write_text("[" + ("{}" * 100) + "]", encoding="utf-8")
    with pytest.raises(DatasetProfileError, match="Large JSON arrays"):
        DatasetProfiler(max_json_array_bytes=2).profile(str(path))


def test_unsupported_remote_uri_is_explicit() -> None:
    with pytest.raises(DatasetProfileError, match="local dataset paths"):
        DatasetProfiler().profile("hdfs://namenode:9000/data/events.parquet")
