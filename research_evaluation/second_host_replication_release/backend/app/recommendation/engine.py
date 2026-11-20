"""Evidence-gated, explainable architecture ranking."""

from __future__ import annotations

from typing import Any, Literal


OptimizationGoal = Literal["execution_time", "throughput", "latency", "resource_usage", "reliability", "balanced"]


class RecommendationEngine:
    """Rank compatible engines without inventing measurements or predictions."""

    def recommend(
        self,
        classification: dict[str, Any],
        *,
        benchmark_comparison: dict[str, Any] | None = None,
        optimization_goal: OptimizationGoal = "balanced",
        resource_constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        constraints = resource_constraints or {}
        compatible = [
            item for item in classification.get("compatible_engines", []) if item.get("compatible")
        ]
        ranked_evidence = list((benchmark_comparison or {}).get("ranked_engines", []))
        if optimization_goal == "throughput":
            ranked_evidence.sort(
                key=lambda item: item.get("mean_throughput_records_per_second")
                if isinstance(item.get("mean_throughput_records_per_second"), (int, float))
                else float("-inf"),
                reverse=True,
            )
        elif optimization_goal == "reliability":
            ranked_evidence.sort(key=lambda item: item.get("successful_measured_runs", 0), reverse=True)
        evidence_by_engine = {item.get("engine"): item for item in ranked_evidence}
        candidates: list[dict[str, Any]] = []
        for item in compatible:
            engine = item["engine"]
            evidence = evidence_by_engine.get(engine)
            score = 50.0
            reasons = [f"{engine} satisfies the classified workload capability requirements."]
            if evidence:
                position = ranked_evidence.index(evidence)
                score += max(0.0, 30.0 - position * 10.0)
                reasons.append(
                    f"Verified benchmark evidence has {evidence['successful_measured_runs']} correct measured run(s)."
                )
                if optimization_goal in {"execution_time", "latency", "balanced"}:
                    reasons.append(
                        f"Mean measured end-to-end time: {evidence['mean_end_to_end_seconds']:.3f} seconds."
                    )
                if optimization_goal == "throughput" and evidence.get("mean_throughput_records_per_second") is not None:
                    reasons.append(
                        f"Mean measured throughput: {evidence['mean_throughput_records_per_second']:.3f} records/sec."
                    )
                if optimization_goal == "reliability":
                    score += 5.0 if item.get("capabilities", {}).get("recovery_signals") else 0.0
            else:
                reasons.append("No correctness-passed benchmark evidence is available for this engine.")
            limits = item.get("capabilities", {}).get("limitations", [])
            if limits:
                reasons.append(f"Known capability limitations: {', '.join(limits)}")
            candidates.append({
                "engine": engine,
                "score": round(score, 3),
                "benchmark_evidence": evidence,
                "reasons": reasons,
                "resource_configuration": (evidence or {}).get("recommended_configuration"),
            })

        candidates.sort(key=lambda item: (-item["score"], item["engine"]))
        enough_evidence = bool(ranked_evidence and candidates and candidates[0].get("benchmark_evidence"))
        status = "RECOMMENDED" if enough_evidence else "INSUFFICIENT_BENCHMARK_EVIDENCE"
        selected = candidates[0] if enough_evidence else None
        return {
            "status": status,
            "selected_engine": selected["engine"] if selected else None,
            "recommended_architecture": {
                "engine": selected["engine"],
                "resource_configuration": selected.get("resource_configuration"),
            } if selected else None,
            "optimization_goal": optimization_goal,
            "resource_constraints": constraints,
            "suitability": "verified_for_this_workload" if selected else "not_established",
            "supporting_benchmark_measurements": ranked_evidence,
            "known_limitations": [
                "This recommendation is workload-specific and is not a universal engine ranking.",
                "Resource utilization is not measured when the benchmark evidence marks it unavailable.",
            ],
            "alternative_configurations": candidates[1:] if selected else candidates,
            "tradeoff_explanation": (
                selected["reasons"] if selected else [
                    "A recommendation requires at least one correctness-passed measured benchmark run.",
                    "Create and execute a benchmark campaign for compatible candidates before deployment.",
                ]
            ),
            "confidence": "measured" if selected else "insufficient_evidence",
            "evidence_provenance": {
                "classification_method": classification.get("explanation", {}).get("method"),
                "benchmark_comparison_present": benchmark_comparison is not None,
                "benchmark_ranking_scope": "correct_successful_measured_runs_only",
                "no_estimates_used": True,
            },
            "proposed_benchmark_plan": classification.get("recommended_benchmark_plan"),
        }
