"""Flink REST adapter with explicit artifact and compatibility boundaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import get_settings
from app.engines.base import EngineAdapter, EngineCompatibilityError
from app.engines.capabilities import flink_capability
from app.engines.models import (
    EngineExecutionPlan,
    EngineJobHandle,
    EngineJobStatus,
    EngineValidationResult,
)
from app.pipeline.config_models import PipelineConfig


class FlinkEngineAdapter(EngineAdapter):
    """Adapter for the Flink JobManager REST API.

    The adapter never substitutes Spark when Flink is unavailable. A Flink
    submission requires a verified artifact path, which is supplied by the
    later Flink job packaging work.
    """

    name = "flink"

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 10.0) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.FLINK_JOBMANAGER_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def capability(self):
        return flink_capability()

    async def health_check(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/overview")
                response.raise_for_status()
                payload = response.json()
            return {
                "connected": True,
                "status": "RUNNING",
                "version": payload.get("flink-version"),
                "taskmanagers": payload.get("taskmanagers", 0),
                "slots_total": payload.get("slots-total", 0),
                "slots_available": payload.get("slots-available", 0),
                "error": None,
            }
        except Exception as exc:
            return {
                "connected": False,
                "status": "UNREACHABLE",
                "version": None,
                "taskmanagers": 0,
                "slots_total": 0,
                "slots_available": 0,
                "error": str(exc),
            }

    async def validate_pipeline(self, config: PipelineConfig) -> EngineValidationResult:
        capability = self.capability()
        errors: list[str] = []
        warnings: list[str] = []
        if config.processing_engine and config.processing_engine.type not in ("flink", "auto"):
            errors.append("Pipeline engine selection is not Flink.")
        for operation in config.processing.operations:
            operation_type = operation.model_dump()["type"]
            if operation_type not in capability.supported_operations:
                errors.append(f"Flink adapter does not support operation '{operation_type}'.")
        if config.source.type not in capability.supported_sources:
            errors.append(f"Flink adapter does not support source '{config.source.type}'.")
        if config.storage.type not in capability.supported_storages:
            errors.append(f"Flink adapter does not support storage '{config.storage.type}'.")
        if config.streaming.enabled and config.messaging is None:
            errors.append("Flink streaming requires a Kafka messaging configuration.")
        if config.processing_engine and config.processing_engine.type == "auto":
            warnings.append("Automatic selection must resolve Flink from verified benchmark evidence before submission.")
        return EngineValidationResult(
            engine="flink",
            compatible=not errors,
            errors=errors,
            warnings=warnings,
            capabilities=capability,
        )

    def generate_plan(self, config: PipelineConfig, *, input_source: str | None = None,
                      output_path: str | None = None, artifact_path: str | None = None) -> EngineExecutionPlan:
        return EngineExecutionPlan(
            engine="flink",
            pipeline_name=config.pipeline.name,
            pipeline_version=config.pipeline.version,
            mode="streaming" if config.streaming.enabled else "batch",
            input_source=input_source or config.source.path,
            output_path=output_path or config.storage.path,
            operations=[operation.model_dump() for operation in config.processing.operations],
            schema=[column.model_dump() for column in config.pipeline_schema],
            engine_options={"streaming": config.streaming.model_dump()},
            artifact_path=artifact_path,
        )

    async def submit(self, plan: EngineExecutionPlan, *, run_id: str | None = None,
                     on_progress: Callable[[dict[str, Any]], None] | None = None) -> EngineJobHandle:
        del run_id, on_progress
        if not plan.artifact_path:
            raise EngineCompatibilityError(
                "Flink submission requires a verified Flink job artifact; no artifact was supplied."
            )
        raise EngineCompatibilityError(
            "Flink artifact submission is not enabled until the Kafka/HDFS job artifact is verified."
        )

    async def get_status(self, job_id: str) -> EngineJobStatus:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/jobs/{job_id}")
                response.raise_for_status()
                payload = response.json()
            raw_state = str(payload.get("state", "UNKNOWN")).upper()
            state = {
                "CREATED": "submitted",
                "RUNNING": "running",
                "FINISHED": "succeeded",
                "CANCELED": "cancelled",
                "FAILED": "failed",
            }.get(raw_state, "unknown")
            return EngineJobStatus(engine="flink", job_id=job_id, state=state, raw_state=raw_state)
        except Exception as exc:
            return EngineJobStatus(engine="flink", job_id=job_id, state="unknown", error=str(exc))

    async def get_metrics(self, job_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/jobs/{job_id}/metrics")
            response.raise_for_status()
            return {"raw": response.json()}

    async def get_logs(self, job_id: str) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/jobs/{job_id}/exceptions")
            response.raise_for_status()
            payload = response.json()
        return [str(item.get("exception")) for item in payload.get("root-exception", [])] if isinstance(payload, dict) else []

    async def cancel(self, job_id: str) -> EngineJobStatus:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.patch(f"{self.base_url}/jobs/{job_id}", params={"mode": "cancel"})
            response.raise_for_status()
        return await self.get_status(job_id)

    async def checkpoint_info(self, job_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/jobs/{job_id}/checkpoints")
            response.raise_for_status()
            return response.json()
