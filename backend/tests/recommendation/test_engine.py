from __future__ import annotations

from app.recommendation.engine import RecommendationEngine


def _classification() -> dict:
    return {
        "compatible_engines": [
            {"engine": "spark", "compatible": True, "errors": [], "capabilities": {"limitations": []}},
            {"engine": "flink", "compatible": True, "errors": [], "capabilities": {"limitations": ["artifact required"]}},
        ],
        "recommended_benchmark_plan": {"candidates": [{"engine": "spark"}, {"engine": "flink"}]},
        "explanation": {"method": "deterministic_rule_based_v1"},
    }


def test_recommendation_uses_only_correctness_passed_benchmark_evidence() -> None:
    result = RecommendationEngine().recommend(
        _classification(),
        benchmark_comparison={
            "ranked_engines": [
                {
                    "engine": "spark",
                    "successful_measured_runs": 1,
                    "mean_end_to_end_seconds": 2.0,
                    "mean_throughput_records_per_second": 5.0,
                    "recommended_configuration": {"parallelism": 2},
                    "confidence": "limited",
                }
            ]
        },
        optimization_goal="throughput",
    )

    assert result["status"] == "RECOMMENDED"
    assert result["selected_engine"] == "spark"
    assert result["recommended_architecture"]["resource_configuration"] == {"parallelism": 2}
    assert result["evidence_provenance"]["no_estimates_used"] is True


def test_recommendation_returns_insufficient_evidence_without_ranked_runs() -> None:
    result = RecommendationEngine().recommend(_classification())

    assert result["status"] == "INSUFFICIENT_BENCHMARK_EVIDENCE"
    assert result["selected_engine"] is None
    assert {item["engine"] for item in result["alternative_configurations"]} == {"spark", "flink"}
