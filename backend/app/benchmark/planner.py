"""Fair benchmark plan generation and measured-result comparison."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.engines.capabilities import flink_capability, spark_capability


Engine = Literal["spark", "flink"]


class BenchmarkCandidate(BaseModel):
    engine: Engine
    worker_count: int = Field(default=1, ge=1, le=100)
    cpu_cores: int = Field(default=2, ge=1, le=256)
    memory_mb: int = Field(default=2048, ge=256, le=1_048_576)
    input_partitions: int = Field(default=1, ge=1, le=10_000)
    parallelism: int = Field(default=2, ge=1, le=10_000)
    trigger_interval_seconds: int | None = Field(default=None, ge=1, le=86_400)
    checkpoint_interval_seconds: int | None = Field(default=None, ge=1, le=86_400)


FAIRNESS_CONTRACT: dict[str, Any] = {
    "same_input_identity": True,
    "same_logical_operations": True,
    "same_output_correctness_contract": True,
    "same_repetition_policy": True,
    "warmup_runs_excluded_from_measurements": True,
    "resource_configuration_recorded": True,
    "software_versions_recorded": True,
    "missing_measurements_are_explicit": True,
}


class BenchmarkPlanner:
    """Generate only candidates compatible with a classified workload."""

    def generate(
        self,
        classification: dict[str, Any],
        *,
        candidates: Iterable[BenchmarkCandidate] | None = None,
        repetitions: int = 3,
        warmup_runs: int = 1,
    ) -> dict[str, Any]:
        if not 1 <= repetitions <= 10:
            raise ValueError("repetitions must be between 1 and 10")
        if not 0 <= warmup_runs <= 5:
            raise ValueError("warmup_runs must be between 0 and 5")

        compatibility = {
            item["engine"]: item for item in classification.get("compatible_engines", [])
        }
        requested = list(candidates or [])
        if not requested:
            requested = [
                BenchmarkCandidate(engine=item["engine"])
                for item in classification.get("recommended_benchmark_plan", {}).get("candidates", [])
                if item.get("engine") in {"spark", "flink"}
            ]
        if not requested:
            requested = [BenchmarkCandidate(engine="spark")]

        selected: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for candidate in requested:
            item = compatibility.get(candidate.engine)
            if item is None:
                rejected.append({"candidate": candidate.model_dump(), "reason": "engine was not classified"})
                continue
            if not item.get("compatible", False):
                rejected.append({"candidate": candidate.model_dump(), "reason": item.get("errors", [])})
                continue
            selected.append(candidate.model_dump())
        if not selected:
            raise ValueError("No requested benchmark candidate is compatible with this workload")

        return {
            "version": "benchmark_plan_v1",
            "candidates": selected,
            "rejected_candidates": rejected,
            "repetitions": repetitions,
            "warmup_runs": warmup_runs,
            "fairness_contract": FAIRNESS_CONTRACT,
            "comparison_policy": {
                "winner_requires_success": True,
                "winner_requires_correctness": True,
                "winner_metric": "end_to_end_seconds",
                "no_universal_engine_claim": True,
            },
        }


def empty_metrics() -> dict[str, Any]:
    """Return a metric envelope where unavailable measurements stay explicit."""
    return {
        "end_to_end_seconds": None,
        "throughput_records_per_second": None,
        "processing_latency_seconds": None,
        "checkpoint_overhead_seconds": None,
        "failure_recovery_seconds": None,
        "data_loss_indicators": None,
        "duplicate_output_indicators": None,
        "measurement_status": "not_measured",
    }


def compare_measured_runs(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compare measured runs without treating failed/incomplete data as wins."""
    by_engine: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        if run.get("is_warmup") or run.get("status") != "succeeded":
            continue
        if run.get("correctness", {}).get("status") != "passed":
            continue
        engine = str(run.get("engine"))
        metrics = run.get("metrics") or {}
        duration = metrics.get("end_to_end_seconds")
        if not isinstance(duration, (int, float)) or duration <= 0:
            continue
        by_engine.setdefault(engine, []).append(run)

    summaries: list[dict[str, Any]] = []
    for engine, engine_runs in sorted(by_engine.items()):
        durations = [float(run["metrics"]["end_to_end_seconds"]) for run in engine_runs]
        throughputs = [
            float(run["metrics"]["throughput_records_per_second"])
            for run in engine_runs
            if isinstance(run.get("metrics", {}).get("throughput_records_per_second"), (int, float))
        ]
        summaries.append({
            "engine": engine,
            "successful_measured_runs": len(engine_runs),
            "mean_end_to_end_seconds": sum(durations) / len(durations),
            "min_end_to_end_seconds": min(durations),
            "mean_throughput_records_per_second": (sum(throughputs) / len(throughputs)) if throughputs else None,
            "recommended_configuration": engine_runs[0].get("configuration"),
            "confidence": "limited" if len(engine_runs) < 3 else "measured",
        })
    ranked = sorted(summaries, key=lambda item: item["mean_end_to_end_seconds"])
    return {
        "ranked_engines": ranked,
        "winner": ranked[0]["engine"] if ranked else None,
        "winner_basis": "lowest mean measured end-to-end time among correct successful runs" if ranked else None,
        "excluded_runs_requirements": [
            "warm-up runs",
            "failed runs",
            "runs without measured duration",
            "runs without independent correctness status=passed",
        ],
    }
