from __future__ import annotations

import pytest

from app.reconfiguration.state import ReconfigurationStateError, preflight_recommendation, transition


def test_reconfiguration_requires_preflight_before_approval() -> None:
    assert transition("proposed", "preflight_passed") == "preflight_passed"
    assert transition("preflight_passed", "approved") == "approved"
    assert transition("approved", "executing") == "executing"
    assert transition("executing", "succeeded") == "succeeded"
    assert transition("succeeded", "rolled_back") == "rolled_back"
    with pytest.raises(ReconfigurationStateError):
        transition("proposed", "approved")


def test_reconfiguration_cannot_rollback_before_verified_success() -> None:
    with pytest.raises(ReconfigurationStateError):
        transition("approved", "rolled_back")
    with pytest.raises(ReconfigurationStateError):
        transition("executing", "rolled_back")


def test_preflight_blocks_unavailable_or_unverified_recommendation() -> None:
    result = preflight_recommendation(
        {"status": "INSUFFICIENT_BENCHMARK_EVIDENCE", "selected_engine": None, "result": {}},
        target_health={"connected": False, "error": "offline"},
        current_engine="spark",
    )

    assert result["status"] == "blocked"
    assert result["mutation_applied"] is False
    assert all(check["passed"] is False for check in result["checks"] if check["name"] in {"recommendation_status", "target_engine_exists", "target_engine_connected"})


def test_preflight_records_explicit_target_engine_override() -> None:
    result = preflight_recommendation(
        {"status": "RECOMMENDED", "selected_engine": "spark", "result": {"evidence_provenance": {"no_estimates_used": True}}},
        target_health={"connected": True},
        current_engine="spark",
        target_engine="flink",
        overrides={"parallelism": 2},
    )

    assert result["target_engine"] == "flink"
    assert result["requested_overrides"] == {"parallelism": 2}


def test_reconfiguration_routes_require_authentication() -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    assert TestClient(app).get("/api/reconfigurations").status_code == 401
