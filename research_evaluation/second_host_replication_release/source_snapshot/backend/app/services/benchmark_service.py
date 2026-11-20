"""Benchmark campaign orchestration with real-or-explicitly-missing evidence."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.benchmark.planner import compare_measured_runs, empty_metrics
from app.database.session import SyncSessionLocal
from app.engines.base import EngineCompatibilityError, EngineUnavailableError
from app.engines.registry import get_engine_adapter
from app.models.benchmark_campaign import BenchmarkCampaign, BenchmarkRun
from app.models.workload_definition import WorkloadDefinition
from app.metrics import transformation_benchmark_duration_seconds, transformation_benchmark_runs_total
from app.pipeline.exceptions import ConfigParseError, ConfigValidationError
from app.pipeline.parser import PipelineConfigParser
from app.pipeline.validator import PipelineBusinessValidator

logger = logging.getLogger(__name__)
_parser = PipelineConfigParser()
_validator = PipelineBusinessValidator()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _engine_config(config: Any, engine: str) -> Any:
    """Clone a logical config for the candidate without mutating the workload."""
    processing_engine = config.processing_engine.model_copy(update={"type": engine}) if config.processing_engine else None
    if processing_engine is None:
        from app.pipeline.config_models import ProcessingEngineConfig

        processing_engine = ProcessingEngineConfig(type=engine, selection_mode="manual")
    return config.model_copy(update={"processing_engine": processing_engine})


def _correctness(config: Any, output_path: str, profile: dict[str, Any] | None) -> dict[str, Any]:
    """Run an independent bounded verifier when the contract supports it."""
    source = config.source.path
    profile_hash = (profile or {}).get("dataset", {}).get("sha256")
    output_location = {"storage_type": config.storage.type, "path": output_path}
    config_dict = config.model_dump(by_alias=True)
    try:
        if (
            config.source.type == "csv"
            and not config.streaming.enabled
            and [item["type"] for item in config_dict["processing"]["operations"]]
            == ["remove_nulls", "remove_duplicates", "filter", "aggregate"]
        ):
            from app.reliability.aggregate_consistency_validator import AggregateConsistencyValidator

            result = AggregateConsistencyValidator().validate(
                output_location=output_location,
                pipeline_config=config_dict,
                writer_stopped=True,
                expected_source_sha256=profile_hash,
            )
        else:
            from app.reliability.data_consistency_validator import DataConsistencyValidator

            result = DataConsistencyValidator().validate(
                output_location=output_location,
                pipeline_config=config_dict,
                writer_stopped=True,
                expected_source_sha256=profile_hash,
            )
        status = {
            "PASS": "passed",
            "FAIL": "failed",
            "UNKNOWN": "unknown",
        }.get(result.get("validation_status"), "unknown")
        return {"status": status, "validator": result}
    except Exception as exc:  # independent verification must never hide run evidence
        return {
            "status": "unknown",
            "validator": None,
            "reason": f"Correctness verifier unavailable: {type(exc).__name__}: {exc}",
            "source": source,
        }


def _metrics(raw: dict[str, Any], elapsed: float) -> dict[str, Any]:
    result = empty_metrics()
    duration = float(elapsed)
    result.update(
        {
            "end_to_end_seconds": duration,
            "engine_reported_duration_seconds": raw.get("duration_seconds"),
            "input_records": raw.get("input_rows"),
            "output_records": raw.get("output_rows"),
            "measurement_status": "measured",
        }
    )
    if isinstance(raw.get("output_rows"), (int, float)) and duration > 0:
        result["throughput_records_per_second"] = float(raw["output_rows"]) / duration
    return result


async def _execute_run(
    db: Any,
    campaign: BenchmarkCampaign,
    run: BenchmarkRun,
    workload: WorkloadDefinition,
    profile: dict[str, Any] | None,
) -> None:
    config = _parser.parse_string(workload.pipeline_yaml)
    validation_errors = _validator.validate(config)
    if validation_errors:
        raise ValueError(f"Workload validation failed: {validation_errors}")
    candidate_config = _engine_config(config, run.engine)
    adapter = get_engine_adapter(run.engine)

    run.status = "running"
    run.started_at = _now()
    db.commit()
    health = await adapter.health_check()
    run.resource_metrics = {
        "availability": health,
        "requested": run.configuration,
        "measured": {
            "cpu_percent": None,
            "memory_bytes": None,
            "resource_measurement_status": "not_measured",
        },
    }
    run.software_versions = {
        "engine": run.engine,
        "capability_version": adapter.capability().version,
        "runtime_version": health.get("version"),
    }
    db.commit()
    if not health.get("connected", False):
        raise EngineUnavailableError(f"{run.engine} is unavailable: {health.get('error') or health.get('status')}")

    validation = await adapter.validate_pipeline(candidate_config)
    if not validation.compatible:
        raise EngineCompatibilityError("; ".join(validation.errors))

    output_path = f"hdfs://namenode:9000/data/chaosflow-benchmarks/{campaign.id}/{run.id}"
    plan = adapter.generate_plan(candidate_config, input_source=candidate_config.source.path, output_path=output_path)
    started = time.monotonic()
    handle = await adapter.submit(plan, run_id=str(run.id))
    elapsed = time.monotonic() - started
    run.metrics = _metrics(handle.metadata or {}, elapsed)
    transformation_benchmark_duration_seconds.labels(engine=run.engine).observe(elapsed)
    run.correctness = _correctness(candidate_config, output_path, profile)
    run.status = "succeeded" if run.correctness.get("status") in {"passed", "unknown"} else "failed"
    transformation_benchmark_runs_total.labels(engine=run.engine, status=run.status).inc()
    run.finished_at = _now()
    db.commit()


def run_benchmark_campaign(campaign_id: str) -> None:
    """Thread entrypoint used by FastAPI; all attempts are durably retained."""
    asyncio.run(_run_benchmark_campaign(campaign_id))


async def _run_benchmark_campaign(campaign_id: str) -> None:
    with SyncSessionLocal() as db:
        campaign = db.get(BenchmarkCampaign, uuid.UUID(campaign_id))
        if campaign is None:
            return
        workload = db.get(WorkloadDefinition, campaign.workload_definition_id)
        if workload is None:
            campaign.status = "failed"
            campaign.error_message = "Workload definition no longer exists."
            campaign.finished_at = _now()
            db.commit()
            return
        campaign.status = "running"
        campaign.started_at = _now()
        db.commit()
        profile = None
        if campaign.dataset_profile_id:
            from app.models.dataset_profile import DatasetProfile

            profile_row = db.get(DatasetProfile, campaign.dataset_profile_id)
            profile = profile_row.result if profile_row else None

        succeeded = 0
        for candidate in campaign.plan.get("candidates", []):
            for repetition in range(0, campaign.repetitions + campaign.warmup_runs):
                is_warmup = repetition < campaign.warmup_runs
                run = BenchmarkRun(
                    campaign_id=campaign.id,
                    engine=candidate["engine"],
                    repetition=repetition if not is_warmup else repetition + 1,
                    is_warmup=is_warmup,
                    status="queued",
                    configuration=candidate,
                    metrics=empty_metrics(),
                    resource_metrics={},
                    correctness={"status": "not_measured"},
                    software_versions={},
                )
                db.add(run)
                db.commit()
                try:
                    await _execute_run(db, campaign, run, workload, profile)
                    if run.status == "succeeded" and not is_warmup:
                        succeeded += 1
                except Exception as exc:
                    logger.warning("Benchmark run %s failed: %s", run.id, exc)
                    run.status = "failed"
                    run.error_message = str(exc)
                    run.metrics = {**empty_metrics(), "failure_reason": str(exc)}
                    run.correctness = {"status": "unknown", "reason": "Run did not produce output for verification."}
                    run.finished_at = _now()
                    db.commit()
                    transformation_benchmark_runs_total.labels(engine=run.engine, status="failed").inc()

        campaign.status = "succeeded" if succeeded else "failed"
        if not succeeded:
            campaign.error_message = "No measured benchmark run completed with usable evidence."
        campaign.finished_at = _now()
        db.commit()


def comparison_for_campaign(campaign: BenchmarkCampaign) -> dict[str, Any]:
    return compare_measured_runs(
        [
            {
                "engine": run.engine,
                "is_warmup": run.is_warmup,
                "status": run.status,
                "metrics": run.metrics,
                "correctness": run.correctness,
                "configuration": run.configuration,
            }
            for run in campaign.runs
        ]
    )
