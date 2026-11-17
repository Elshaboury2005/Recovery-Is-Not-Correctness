"""Regression tests for authentication on sensitive APIs."""

from fastapi.testclient import TestClient

from app.main import app


def test_pipeline_validation_requires_authentication() -> None:
    response = TestClient(app).post(
        "/api/pipelines/validate",
        json={"yaml_content": "pipeline:\n  name: unauthenticated"},
    )
    assert response.status_code == 401


def test_pipeline_execution_requires_authentication() -> None:
    response = TestClient(app).post(
        "/api/pipelines/run",
        json={"yaml_content": "pipeline:\n  name: unauthenticated"},
    )
    assert response.status_code == 401


def test_kafka_topic_mutation_requires_authentication() -> None:
    response = TestClient(app).post(
        "/api/messaging/topics",
        json={"topic": "unauthenticated-topic"},
    )
    assert response.status_code == 401


def test_sensitive_metrics_requires_authentication() -> None:
    response = TestClient(app).get("/api/metrics")
    assert response.status_code == 401


def test_reliability_analysis_requires_authentication() -> None:
    response = TestClient(app).post(
        "/api/ai/reliability-analysis",
        json={"observations": [{"latency": 1.0}]},
    )
    assert response.status_code == 401
