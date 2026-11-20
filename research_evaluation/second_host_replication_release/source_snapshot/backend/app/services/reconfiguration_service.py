"""Controlled reconfiguration execution with isolated correctness verification.

An approved operation never rewires a live pipeline in this service.  It runs
the recommended engine against the workload into a unique HDFS evidence path,
validates the output independently, and records whether that isolated check
passed.  This keeps the execution boundary auditable until a deployment
controller with an explicit production-routing contract exists.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.benchmark.planner import empty_metrics
from app.database.session import SyncSessionLocal
from app.engines.base import EngineCompatibilityError, EngineUnavailableError
from app.engines.registry import get_engine_adapter
from app.models.architecture_recommendation import ArchitectureRecommendation
from app.models.dataset_profile import DatasetProfile
from app.models.reconfiguration import ReconfigurationOperation
from app.models.workload_definition import WorkloadDefinition
from app.pipeline.exceptions import ConfigParseError, ConfigValidationError
from app.pipeline.parser import PipelineConfigParser
from app.pipeline.validator import PipelineBusinessValidator
from app.reconfiguration.state import transition

from app.services.benchmark_service import _correctness, _engine_config, _metrics


_parser = PipelineConfigParser()
_validator = PipelineBusinessValidator()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _event(action: str, state: str, detail: str) -> dict[str, str]:
    return {"action": action, "state": state, "detail": detail, "timestamp": _now().isoformat()}


def _failure_result(*, reason: str, target_engine: str, output_path: str | None = None) -> dict[str, Any]:
    return {
        "status": "failed",
        "reason": reason,
        "target_engine": target_engine,
        "output_path": output_path,
        "deployment_mode": "isolated_verification",
        "production_mutation_applied": False,
        "rollback_available": False,
        "metrics": empty_metrics(),
        "correctness": {"status": "unknown", "reason": "No verified output was available."},
    }


async def _execute(operation_id: str) -> None:
    with SyncSessionLocal() as db:
        operation = db.get(ReconfigurationOperation, uuid.UUID(operation_id))
        if operation is None or operation.state != "executing":
            return

        output_path: str | None = None
        started = time.monotonic()
        try:
            recommendation = db.get(ArchitectureRecommendation, operation.recommendation_id)
            if recommendation is None:
                raise ValueError("Recommendation no longer exists.")
            workload = db.get(WorkloadDefinition, recommendation.workload_definition_id)
            if workload is None:
                raise ValueError("Workload definition no longer exists.")
            if operation.target_engine not in {"spark", "flink"}:
                raise ValueError(f"Unsupported target engine: {operation.target_engine}")

            config = _parser.parse_string(workload.pipeline_yaml)
            validation_errors = _validator.validate(config)
            if validation_errors:
                raise ValueError(f"Workload validation failed: {validation_errors}")
            if config.streaming.enabled:
                raise EngineCompatibilityError("Controlled reconfiguration currently supports batch workloads only.")
            if not config.source.path:
                raise EngineCompatibilityError("Controlled reconfiguration requires a file-backed source path.")

            candidate_config = _engine_config(config, operation.target_engine)
            adapter = get_engine_adapter(operation.target_engine)
            health = await adapter.health_check()
            if not health.get("connected", False):
                raise EngineUnavailableError(
                    f"{operation.target_engine} is unavailable: {health.get('error') or health.get('status')}"
                )
            compatibility = await adapter.validate_pipeline(candidate_config)
            if not compatibility.compatible:
                raise EngineCompatibilityError("; ".join(compatibility.errors))

            output_path = f"hdfs://namenode:9000/data/chaosflow-reconfigurations/{operation.id}"
            plan = adapter.generate_plan(
                candidate_config,
                input_source=candidate_config.source.path,
                output_path=output_path,
            )
            handle = await adapter.submit(plan, run_id=f"reconfiguration-{operation.id}")

            profile = None
            if workload.dataset_profile_id:
                profile_row = db.get(DatasetProfile, workload.dataset_profile_id)
                profile = profile_row.result if profile_row else None
            correctness = _correctness(candidate_config, output_path, profile)
            metrics = _metrics(handle.metadata or {}, time.monotonic() - started)
            result = {
                "status": "succeeded" if correctness.get("status") == "passed" else "failed",
                "target_engine": operation.target_engine,
                "previous_configuration": {"engine": operation.current_engine},
                "proposed_configuration": {"engine": operation.target_engine, "overrides": operation.requested_overrides},
                "applied_changes": {"mode": "isolated_verification", "production_mutation_applied": False},
                "job_id": handle.job_id,
                "output_path": output_path,
                "deployment_mode": "isolated_verification",
                "production_mutation_applied": False,
                "rollback_available": correctness.get("status") == "passed",
                "engine_health": health,
                "metrics": metrics,
                "correctness": correctness,
                "requested_overrides": operation.requested_overrides,
                "override_application": "recorded_only; no production routing mutation was applied",
            }
            operation.execution_result = result
            operation.error_message = None if result["status"] == "succeeded" else "Independent correctness verification did not pass."
            next_state = "succeeded" if result["status"] == "succeeded" else "failed"
            operation.state = transition(operation.state, next_state)
            operation.audit_events = [
                *operation.audit_events,
                _event("execution_finished", operation.state, result["status"]),
            ]
        except (ConfigParseError, ConfigValidationError, EngineCompatibilityError, EngineUnavailableError, ValueError) as exc:
            operation.execution_result = _failure_result(
                reason=str(exc), target_engine=operation.target_engine, output_path=output_path
            )
            operation.error_message = str(exc)
            operation.state = transition(operation.state, "failed")
            operation.audit_events = [*operation.audit_events, _event("execution_failed", operation.state, str(exc))]
        except Exception as exc:  # retain a durable failure record for unexpected runtime errors
            operation.execution_result = _failure_result(
                reason=f"{type(exc).__name__}: {exc}", target_engine=operation.target_engine, output_path=output_path
            )
            operation.error_message = f"{type(exc).__name__}: {exc}"
            operation.state = transition(operation.state, "failed")
            operation.audit_events = [*operation.audit_events, _event("execution_failed", operation.state, operation.error_message)]
        db.commit()


def run_reconfiguration(operation_id: str) -> None:
    """Thread entrypoint used by FastAPI for an approved operation."""
    asyncio.run(_execute(operation_id))
