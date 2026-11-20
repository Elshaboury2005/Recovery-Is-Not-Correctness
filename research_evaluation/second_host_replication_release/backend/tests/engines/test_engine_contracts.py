from __future__ import annotations

import pytest

from app.engines.flink import FlinkEngineAdapter
from app.engines.models import EngineExecutionPlan
from app.engines.spark import SparkEngineAdapter
from app.pipeline.config_models import PipelineConfig
from app.pipeline.validator import PipelineBusinessValidator


def _config(*, engine: str = "spark", source: str = "csv", operation: str = "filter") -> PipelineConfig:
    data = {
        "pipeline": {"name": "engine-contract", "version": "1.0"},
        "source": {"type": source, "path": "/app/sample-data/sales_sample.csv"},
        "schema": [
            {"name": "customer_id", "type": "string"},
            {"name": "amount", "type": "double"},
        ],
        "processing": {"operations": [{"type": operation, "condition": "amount > 0"}]},
        "streaming": {"enabled": False},
        "processing_engine": {"type": engine},
        "storage": {"type": "hdfs", "path": "/output/engine-contract"},
    }
    return PipelineConfig.model_validate(data)


@pytest.mark.asyncio
async def test_spark_adapter_preserves_existing_capability_surface() -> None:
    result = await SparkEngineAdapter().validate_pipeline(_config())
    assert result.compatible is True
    assert "aggregate" in result.capabilities.supported_operations
    assert result.capabilities.supports_streaming is True


@pytest.mark.asyncio
async def test_flink_rejects_unsupported_batch_csv_before_submission() -> None:
    result = await FlinkEngineAdapter(base_url="http://127.0.0.1:1").validate_pipeline(
        _config(engine="flink")
    )
    assert result.compatible is False
    assert any("source 'csv'" in error for error in result.errors)


def test_flink_plan_is_explicit_about_missing_artifact() -> None:
    plan = FlinkEngineAdapter().generate_plan(_config(engine="flink"))
    assert plan.engine == "flink"
    assert plan.artifact_path is None
    assert plan.output_path == "/output/engine-contract"


def test_auto_selection_requires_non_manual_policy() -> None:
    config = _config(engine="auto")
    errors = PipelineBusinessValidator().validate(config)
    assert any(error["field"] == "processing_engine.selection_mode" for error in errors)


def test_verified_benchmark_selection_requires_evidence_id() -> None:
    config = _config(engine="auto")
    config.processing_engine.selection_mode = "verified_benchmark"
    errors = PipelineBusinessValidator().validate(config)
    assert any(error["field"] == "processing_engine.benchmark_id" for error in errors)


@pytest.mark.asyncio
async def test_flink_submission_never_silently_falls_back_to_spark() -> None:
    plan = EngineExecutionPlan(
        engine="flink",
        pipeline_name="engine-contract",
        pipeline_version="1.0",
        mode="batch",
        output_path="/output/engine-contract",
    )
    with pytest.raises(ValueError, match="verified Flink job artifact"):
        await FlinkEngineAdapter().submit(plan)
