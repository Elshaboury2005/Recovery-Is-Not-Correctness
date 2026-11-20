from __future__ import annotations

from app.services.pipeline_execution_service import run_pipeline_from_yaml


def test_explicit_flink_request_is_rejected_before_legacy_executor() -> None:
    yaml_content = """
pipeline:
  name: flink-csv-guard
  version: '1.0'
source:
  type: csv
  path: /app/sample-data/sales_sample.csv
schema:
  - name: customer_id
    type: string
processing:
  operations:
    - type: filter
      condition: customer_id == 'c1'
streaming:
  enabled: false
processing_engine:
  type: flink
storage:
  type: hdfs
  path: /output/flink-csv-guard
"""
    result = run_pipeline_from_yaml(yaml_content)
    assert result["status"] == "invalid"
    assert result["run_id"] is None
    assert any("source 'csv'" in error["message"] for error in result["errors"])


def test_auto_request_does_not_fallback_to_spark() -> None:
    yaml_content = """
pipeline:
  name: auto-guard
  version: '1.0'
source:
  type: csv
  path: /app/sample-data/sales_sample.csv
schema:
  - name: customer_id
    type: string
processing:
  operations:
    - type: filter
      condition: customer_id == 'c1'
streaming:
  enabled: false
processing_engine:
  type: auto
  selection_mode: automatic_recommendation
storage:
  type: hdfs
  path: /output/auto-guard
"""
    result = run_pipeline_from_yaml(yaml_content)
    assert result["status"] == "invalid"
    assert "recommendation service" in result["errors"][0]["message"]
