from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_topology_route_requires_authentication() -> None:
    assert TestClient(app).get("/api/infrastructure/topology").status_code == 401


def test_topology_discovery_reports_unavailable_without_fabricating_nodes() -> None:
    with patch.dict("sys.modules", {"docker": None}):
        from app.infrastructure.topology import discover_topology

        result = discover_topology()

    assert result["status"] == "unavailable"
    assert result["nodes"] == []
    assert result["edges"] == []


def test_topology_comparison_does_not_fabricate_planned_containers() -> None:
    from types import SimpleNamespace

    from app.infrastructure.topology import compare_topology

    topology = {
        "status": "ready",
        "generated_at": "2026-11-06T00:00:00+00:00",
        "nodes": [{"role": "spark-master"}],
        "edges": [],
    }
    recommendation = SimpleNamespace(
        id="rec-1",
        status="RECOMMENDED",
        selected_engine="flink",
        optimization_goal="throughput",
        result={
            "recommended_architecture": {"engine": "flink", "resource_configuration": None},
            "confidence": "measured",
            "evidence_provenance": {"no_estimates_used": True},
        },
    )

    result = compare_topology(topology, recommendation)

    assert result["status"] == "ready"
    assert result["planned"]["engine"] == "flink"
    assert result["changes"][0]["status"] == "planned_only"
    assert "nodes" not in result["planned"]


def test_topology_comparison_without_recommendation_is_explicit() -> None:
    from app.infrastructure.topology import compare_topology

    result = compare_topology({"status": "ready", "generated_at": "now", "nodes": [], "edges": []})

    assert result["status"] == "no_plan"
    assert result["planned"] is None
