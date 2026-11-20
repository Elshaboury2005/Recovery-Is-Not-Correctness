"""Explainable workload classification and engine capability matching."""

from __future__ import annotations

from typing import Any

from app.engines.capabilities import flink_capability, spark_capability
from app.pipeline.config_models import PipelineConfig


class WorkloadClassifier:
    """Rule-based baseline; no unverified ML claim is made."""

    def classify(
        self,
        config: PipelineConfig,
        profile: dict[str, Any] | None = None,
        user_constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = profile or {}
        constraints = user_constraints or {}
        operations = [operation.model_dump()["type"] for operation in config.processing.operations]
        streaming = bool(config.streaming.enabled)
        record_count = profile.get("record_count", {}).get("value")
        numeric_columns = profile.get("numeric_columns", [])
        timestamp_fields = profile.get("timestamp_fields", [])
        data_quality = profile.get("data_quality", {})
        duplicate_ratio = profile.get("duplicate_characteristics", {}).get("duplicate_ratio", 0)
        skew = profile.get("data_skew", [])

        categories: list[str] = []
        reasons: list[str] = []
        required_capabilities: list[str] = []
        if streaming:
            categories.append("continuous_streaming")
            reasons.append("streaming.enabled is true")
            required_capabilities.extend(["kafka_source", "checkpointing"])
            if config.streaming.trigger_interval_seconds > 1:
                categories.append("micro_batch_streaming")
                reasons.append("a trigger interval is configured")
            if any(operation in operations for operation in ("remove_duplicates", "aggregate")):
                categories.append("stateful_streaming")
                reasons.append("the pipeline contains stateful operations")
                required_capabilities.append("state_management")
            if config.streaming.watermark is not None or timestamp_fields:
                categories.append("event_time_window_processing")
                reasons.append("event-time/watermark metadata is available")
                required_capabilities.append("event_time")
        else:
            categories.append("batch_processing")
            reasons.append("streaming.enabled is false")

        stateful_operations = {"remove_duplicates", "aggregate"}
        if not any(operation in stateful_operations for operation in operations):
            categories.append("stateless_transformation")
            reasons.append("no stateful operation is declared")
        if "aggregate" in operations:
            categories.append("analytical_transformation")
            reasons.append("aggregate operation is declared")
        if any(operation in operations for operation in ("remove_nulls", "type_conversion")) or data_quality.get("quality_issue_count", 0):
            categories.append("data_quality_intensive_processing")
            reasons.append("data-quality operations or issues are present")
        if isinstance(record_count, (int, float)) and record_count >= 1_000_000:
            categories.append("high_throughput_ingestion")
            reasons.append("profiled record count is at least one million")
        latency_target = constraints.get("latency_target_seconds")
        if isinstance(latency_target, (int, float)) and latency_target <= 5:
            categories.append("low_latency_processing")
            reasons.append("user latency target is five seconds or less")

        bottlenecks: list[str] = []
        if duplicate_ratio and duplicate_ratio > 0.05:
            bottlenecks.append("duplicate-heavy input may increase state or deduplication cost")
        if any(float(item.get("top_value_ratio", 0)) >= 0.5 for item in skew):
            bottlenecks.append("skewed key distribution may create uneven parallelism")
        if len(numeric_columns) == 0 and isinstance(record_count, (int, float)) and record_count > 100_000:
            bottlenecks.append("large string-heavy input may increase serialization and memory pressure")
        if data_quality.get("quality_issue_count", 0):
            bottlenecks.append("profiled quality issues require validation/cleaning before comparison")

        engine_results = []
        for capability in (spark_capability(), flink_capability()):
            errors: list[str] = []
            if streaming and not capability.supports_streaming:
                errors.append("streaming is unsupported")
            if config.source.type not in capability.supported_sources:
                errors.append(f"source '{config.source.type}' is unsupported")
            for operation in operations:
                if operation not in capability.supported_operations:
                    errors.append(f"operation '{operation}' is unsupported")
            if config.storage.type not in capability.supported_storages:
                errors.append(f"storage '{config.storage.type}' is unsupported")
            engine_results.append({
                "engine": capability.engine,
                "compatible": not errors,
                "errors": errors,
                "capabilities": capability.model_dump(),
            })

        compatible = [item["engine"] for item in engine_results if item["compatible"]]
        benchmark_candidates = [
            {"engine": engine, "parallelism": 2, "repetitions": 3, "warmup_runs": 1}
            for engine in compatible
        ]
        if not benchmark_candidates:
            benchmark_candidates = [{"engine": "spark", "parallelism": 2, "repetitions": 3, "warmup_runs": 1}]
        return {
            "categories": list(dict.fromkeys(categories)),
            "constraints": constraints,
            "required_capabilities": list(dict.fromkeys(required_capabilities)),
            "compatible_engines": engine_results,
            "potential_bottlenecks": bottlenecks,
            "recommended_benchmark_plan": {
                "candidates": benchmark_candidates,
                "fairness_requirements": [
                    "same input identity",
                    "same logical operations",
                    "same output correctness contract",
                    "record software and resource configuration",
                ],
            },
            "explanation": {
                "method": "deterministic_rule_based_v1",
                "reasons": reasons,
                "profile_evidence": {
                    "record_count": record_count,
                    "numeric_columns": len(numeric_columns),
                    "timestamp_fields": timestamp_fields,
                    "duplicate_ratio": duplicate_ratio,
                },
            },
        }
