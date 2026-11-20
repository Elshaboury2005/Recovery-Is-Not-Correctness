"""Engine-specific ChaosLab readiness and observability contracts."""

from __future__ import annotations

from typing import Any

from app.engines.registry import get_engine_adapter


async def engine_chaos_capabilities() -> list[dict[str, Any]]:
    definitions = {
        "spark": {
            "fault_targets": ["spark-master", "spark-worker"],
            "observability_signals": ["application_state", "stage_progress", "executor_metrics", "output_correctness"],
            "recovery_measurements": ["time_to_recovery", "restart_attempts", "output_integrity"],
            "safety_boundary": "Existing ChaosLab allow-list and project-label validation",
        },
        "flink": {
            "fault_targets": ["flink-jobmanager", "flink-taskmanager"],
            "observability_signals": ["job_state", "checkpoint_state", "taskmanager_slots", "output_correctness"],
            "recovery_measurements": ["checkpoint_recovery_time", "restart_attempts", "output_integrity"],
            "safety_boundary": "Runtime must be enabled and targets must be explicitly safety-allowlisted before injection",
        },
    }
    results = []
    for engine, definition in definitions.items():
        health = await get_engine_adapter(engine).health_check()
        results.append({
            "engine": engine,
            "ready_for_observation": bool(health.get("connected")),
            "ready_for_fault_injection": bool(health.get("connected")) and engine == "spark",
            "health": health,
            **definition,
        })
    return results
