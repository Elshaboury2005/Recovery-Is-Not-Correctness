from __future__ import annotations

from datetime import timedelta

from app.pipeline.config_models import PipelineConfig
from app.workload.classifier import WorkloadClassifier
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app


def _config(streaming: bool = False) -> PipelineConfig:
    return PipelineConfig.model_validate({
        "pipeline": {"name": "classifier-test", "version": "1.0"},
        "source": {"type": "kafka", "topic": "events"} if streaming else {"type": "csv", "path": "/app/sample-data/sales_sample.csv"},
        "schema": [{"name": "event_time", "type": "timestamp"}, {"name": "amount", "type": "double"}],
        "processing": {"operations": [{"type": "remove_nulls"}, {"type": "filter", "condition": "amount > 0"}]},
        "streaming": {"enabled": streaming, "watermark": {"column": "event_time", "delay_seconds": 10} if streaming else None},
        "messaging": {"broker": "kafka", "topic": "events", "partitions": 2} if streaming else None,
        "processing_engine": {"type": "spark"},
        "storage": {"type": "hdfs", "path": "/output/classifier-test"},
    })


def test_batch_classification_is_deterministic_and_explainable() -> None:
    profile = {
        "record_count": {"value": 2_000_000, "scope": "exact"},
        "numeric_columns": ["amount"],
        "timestamp_fields": ["event_time"],
        "duplicate_characteristics": {"duplicate_ratio": 0.1},
        "data_quality": {"quality_issue_count": 1},
        "data_skew": [{"top_value_ratio": 0.7}],
    }
    result = WorkloadClassifier().classify(_config(), profile)
    assert "batch_processing" in result["categories"]
    assert "high_throughput_ingestion" in result["categories"]
    assert result["explanation"]["method"] == "deterministic_rule_based_v1"
    assert any(item["engine"] == "spark" and item["compatible"] for item in result["compatible_engines"])


def test_streaming_state_and_event_time_requirements_are_reported() -> None:
    result = WorkloadClassifier().classify(_config(streaming=True), {"timestamp_fields": ["event_time"]})
    assert "continuous_streaming" in result["categories"]
    assert "event_time_window_processing" in result["categories"]
    assert "checkpointing" in result["required_capabilities"]


def test_workload_history_requires_authentication() -> None:
    assert TestClient(app).get("/api/workloads").status_code == 401


def test_workload_history_authenticated_returns_persisted_shape() -> None:
    token = create_access_token({"sub": "admin"}, timedelta(minutes=15))
    response = TestClient(app).get(
        "/api/workloads",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
