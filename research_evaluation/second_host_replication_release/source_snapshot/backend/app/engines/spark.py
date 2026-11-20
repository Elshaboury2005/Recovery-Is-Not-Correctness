"""Spark adapter that delegates execution to the existing Spark submitter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.engines.base import EngineAdapter, EngineCompatibilityError
from app.engines.capabilities import spark_capability
from app.engines.models import (
    EngineExecutionPlan,
    EngineJobHandle,
    EngineJobStatus,
    EngineValidationResult,
)
from app.pipeline.config_models import PipelineConfig
from app.spark.spark_job_submitter import SparkJobSubmitter


class SparkEngineAdapter(EngineAdapter):
    """Shared-contract facade over the preserved Spark implementation."""

    name = "spark"

    def __init__(self, submitter: SparkJobSubmitter | None = None) -> None:
        self._submitter = submitter or SparkJobSubmitter()
        self._jobs: dict[str, EngineJobStatus] = {}

    def capability(self):
        return spark_capability()

    async def health_check(self) -> dict[str, Any]:
        return await self._submitter.health_check()

    async def validate_pipeline(self, config: PipelineConfig) -> EngineValidationResult:
        capability = self.capability()
        errors: list[str] = []
        warnings: list[str] = []
        if config.processing_engine and config.processing_engine.type not in ("spark", "auto"):
            errors.append("Pipeline engine selection is not Spark.")
        for operation in config.processing.operations:
            operation_type = operation.model_dump()["type"]
            if operation_type not in capability.supported_operations:
                errors.append(f"Spark does not support operation '{operation_type}'.")
        if config.streaming.enabled and config.messaging is None:
            errors.append("Spark streaming requires a Kafka messaging configuration.")
        if config.storage.type not in capability.supported_storages:
            errors.append(f"Spark adapter does not support storage '{config.storage.type}'.")
        if config.storage.type == "local":
            warnings.append("Spark worker visibility requires the executor to normalize local output to HDFS.")
        return EngineValidationResult(
            engine="spark",
            compatible=not errors,
            errors=errors,
            warnings=warnings,
            capabilities=capability,
        )

    def generate_plan(self, config: PipelineConfig, *, input_source: str | None = None,
                      output_path: str | None = None, artifact_path: str | None = None) -> EngineExecutionPlan:
        operations = [operation.model_dump() for operation in config.processing.operations]
        return EngineExecutionPlan(
            engine="spark",
            pipeline_name=config.pipeline.name,
            pipeline_version=config.pipeline.version,
            mode="streaming" if config.streaming.enabled else "batch",
            input_source=input_source or config.source.path,
            output_path=output_path or config.storage.path,
            operations=operations,
            schema=[column.model_dump() for column in config.pipeline_schema],
            engine_options={"streaming": config.streaming.model_dump()},
            artifact_path=artifact_path,
        )

    async def submit(self, plan: EngineExecutionPlan, *, run_id: str | None = None,
                     on_progress: Callable[[dict[str, Any]], None] | None = None) -> EngineJobHandle:
        if plan.mode != "batch":
            raise EngineCompatibilityError(
                "Use the existing Spark streaming coordinator for streaming plans; "
                "the shared adapter will expose it in a later compatibility step."
            )
        if not plan.input_source or not plan.output_path:
            raise EngineCompatibilityError("Spark submission requires input_source and output_path.")
        job_id = run_id or "spark-local-submit"
        self._jobs[job_id] = EngineJobStatus(engine="spark", job_id=job_id, state="running")
        try:
            result = await self._submitter.submit_batch_job(
                input_source=plan.input_source,
                output_path=plan.output_path,
                processing_config={"processing": {"operations": plan.operations}, "schema": plan.pipeline_schema},
                run_id=run_id,
                on_progress=on_progress,
            )
        except Exception as exc:
            self._jobs[job_id] = EngineJobStatus(engine="spark", job_id=job_id, state="failed", error=str(exc))
            raise
        self._jobs[job_id] = EngineJobStatus(
            engine="spark", job_id=job_id, state="succeeded", metrics=result
        )
        return EngineJobHandle(
            engine="spark", job_id=job_id, state="succeeded", output_path=plan.output_path, metadata=result
        )

    async def get_status(self, job_id: str) -> EngineJobStatus:
        return self._jobs.get(
            job_id,
            EngineJobStatus(engine="spark", job_id=job_id, state="unknown", error="No local adapter record for job."),
        )

    async def get_metrics(self, job_id: str) -> dict[str, Any]:
        status = await self.get_status(job_id)
        return dict(status.metrics)

    async def get_logs(self, job_id: str) -> list[str]:
        status = await self.get_status(job_id)
        return [status.error] if status.error else []

    async def cancel(self, job_id: str) -> EngineJobStatus:
        status = await self.get_status(job_id)
        if status.state == "running":
            status = status.model_copy(update={"state": "cancelled"})
            self._jobs[job_id] = status
        return status

    async def checkpoint_info(self, job_id: str) -> dict[str, Any]:
        return {"supported": True, "portable_to_flink": False, "job_id": job_id, "path": None}
