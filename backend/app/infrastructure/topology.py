"""Discover Compose topology for the infrastructure explorer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings


def _role(name: str, labels: dict[str, str]) -> str:
    service = labels.get("com.docker.compose.service", name)
    if service in {"postgres", "kafka", "spark-master", "spark-worker", "namenode", "datanode", "flink-jobmanager", "flink-taskmanager", "hive-metastore", "hive-server"}:
        return service
    return "supporting"


def discover_topology() -> dict[str, Any]:
    settings = get_settings()
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list(all=True, filters={"label": f"com.docker.compose.project={settings.COMPOSE_PROJECT_NAME}"})
        nodes: list[dict[str, Any]] = []
        network_members: dict[str, list[str]] = {}
        for container in containers:
            attrs = container.attrs or {}
            labels = attrs.get("Config", {}).get("Labels", {}) or {}
            networks = attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
            node_id = container.id[:12]
            node = {
                "id": node_id,
                "name": container.name,
                "service": labels.get("com.docker.compose.service"),
                "role": _role(container.name, labels),
                "image": attrs.get("Config", {}).get("Image") or getattr(container, "image", {}).attrs.get("RepoTags", [None])[0],
                "status": container.status,
                "health": (attrs.get("State", {}).get("Health", {}) or {}).get("Status"),
                "networks": sorted(networks),
                "ports": sorted((attrs.get("NetworkSettings", {}).get("Ports", {}) or {}).keys()),
            }
            nodes.append(node)
            for network in networks:
                network_members.setdefault(network, []).append(node_id)
        edges: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for network, members in network_members.items():
            for index, source in enumerate(members):
                for target in members[index + 1:]:
                    key = (min(source, target), max(source, target), network)
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append({"source": source, "target": target, "network": network})
        return {"status": "ready", "generated_at": generated_at, "project": settings.COMPOSE_PROJECT_NAME, "nodes": nodes, "edges": edges, "error": None}
    except Exception as exc:
        return {"status": "unavailable", "generated_at": generated_at, "project": settings.COMPOSE_PROJECT_NAME, "nodes": [], "edges": [], "error": str(exc)}


def compare_topology(topology: dict[str, Any], recommendation: Any | None = None) -> dict[str, Any]:
    """Return a read-only deployed-versus-planned architecture comparison.

    The planned side is deliberately an architecture description from a persisted
    recommendation, not a fabricated list of containers. This keeps the explorer
    honest when an optional engine is unavailable or a recommendation has not been
    established yet.
    """
    current_engines = sorted({
        "spark" if node.get("role") in {"spark-master", "spark-worker"} else "flink"
        for node in topology.get("nodes", [])
        if node.get("role") in {"spark-master", "spark-worker", "flink-jobmanager", "flink-taskmanager"}
    })
    if recommendation is None:
        return {
            "status": "no_plan",
            "generated_at": topology.get("generated_at"),
            "current": topology,
            "planned": None,
            "changes": [],
            "message": "Select a persisted architecture recommendation to compare a planned target.",
        }

    result = recommendation.result or {}
    planned_architecture = result.get("recommended_architecture")
    selected_engine = recommendation.selected_engine
    if not selected_engine and isinstance(planned_architecture, dict):
        selected_engine = planned_architecture.get("engine")
    if not selected_engine:
        return {
            "status": "insufficient_evidence",
            "generated_at": topology.get("generated_at"),
            "current": topology,
            "planned": {
                "recommendation_id": str(recommendation.id),
                "status": recommendation.status,
                "engine": None,
                "architecture": planned_architecture,
                "confidence": result.get("confidence", "insufficient_evidence"),
            },
            "changes": [],
            "message": "The recommendation does not establish a measured target architecture.",
        }

    change_status = "already_deployed" if selected_engine in current_engines else "planned_only"
    return {
        "status": "ready",
        "generated_at": topology.get("generated_at"),
        "current": topology,
        "planned": {
            "recommendation_id": str(recommendation.id),
            "status": recommendation.status,
            "engine": selected_engine,
            "architecture": planned_architecture,
            "confidence": result.get("confidence"),
            "optimization_goal": recommendation.optimization_goal,
        },
        "changes": [{
            "kind": "engine_selection",
            "current_engines": current_engines,
            "planned_engine": selected_engine,
            "status": change_status,
            "evidence_based": result.get("evidence_provenance", {}).get("no_estimates_used") is True,
        }],
        "message": "Planned architecture is sourced from the selected persisted recommendation; runtime mutation is not performed here.",
    }
