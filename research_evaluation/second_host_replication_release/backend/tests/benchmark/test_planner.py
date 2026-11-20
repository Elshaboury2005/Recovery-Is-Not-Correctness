from __future__ import annotations

import pytest

from app.benchmark.planner import BenchmarkCandidate, BenchmarkPlanner, compare_measured_runs


def _classification() -> dict:
    return {
        "compatible_engines": [
            {"engine": "spark", "compatible": True, "errors": []},
            {"engine": "flink", "compatible": False, "errors": ["CSV is unsupported"]},
        ],
        "recommended_benchmark_plan": {"candidates": [{"engine": "spark"}]},
    }


def test_planner_preserves_fairness_and_rejects_incompatible_candidates() -> None:
    plan = BenchmarkPlanner().generate(
        _classification(),
        candidates=[BenchmarkCandidate(engine="spark"), BenchmarkCandidate(engine="flink")],
        repetitions=2,
        warmup_runs=1,
    )

    assert [item["engine"] for item in plan["candidates"]] == ["spark"]
    assert plan["rejected_candidates"][0]["candidate"]["engine"] == "flink"
    assert plan["fairness_contract"]["same_input_identity"] is True
    assert plan["warmup_runs"] == 1


def test_planner_does_not_allow_an_incompatible_only_plan() -> None:
    with pytest.raises(ValueError, match="No requested benchmark candidate"):
        BenchmarkPlanner().generate(
            _classification(), candidates=[BenchmarkCandidate(engine="flink")]
        )


def test_comparison_requires_measured_correct_output() -> None:
    result = compare_measured_runs(
        [
            {"engine": "spark", "status": "succeeded", "is_warmup": False,
             "metrics": {"end_to_end_seconds": 2.0, "throughput_records_per_second": 10},
             "correctness": {"status": "passed"}},
            {"engine": "spark", "status": "succeeded", "is_warmup": True,
             "metrics": {"end_to_end_seconds": 0.1}, "correctness": {"status": "passed"}},
            {"engine": "flink", "status": "succeeded", "is_warmup": False,
             "metrics": {"end_to_end_seconds": 1.0}, "correctness": {"status": "unknown"}},
        ]
    )

    assert result["winner"] == "spark"
    assert result["ranked_engines"][0]["successful_measured_runs"] == 1


def test_benchmark_routes_require_authentication() -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    assert TestClient(app).get("/api/benchmarks").status_code == 401
