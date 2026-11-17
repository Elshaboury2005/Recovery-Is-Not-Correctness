"""Explicit state transitions for safe architecture changes."""

from __future__ import annotations

from typing import Final


class ReconfigurationStateError(ValueError):
    """Raised when a lifecycle transition would bypass a safety gate."""


TRANSITIONS: Final[dict[str, set[str]]] = {
    "proposed": {"preflight_passed", "blocked"},
    "preflight_passed": {"approved", "blocked"},
    "approved": {"executing", "blocked"},
    "executing": {"succeeded", "failed"},
    "succeeded": {"rolled_back"},
    "failed": {"proposed"},
    "blocked": {"proposed"},
    "rolled_back": set(),
}


def transition(current: str, target: str) -> str:
    if target not in TRANSITIONS.get(current, set()):
        raise ReconfigurationStateError(f"Cannot transition reconfiguration from {current!r} to {target!r}")
    return target


def preflight_recommendation(
    recommendation: dict,
    *,
    target_health: dict,
    current_engine: str | None,
    target_engine: str | None = None,
    overrides: dict | None = None,
) -> dict:
    """Return auditable preflight evidence without mutating runtime state."""
    overrides = overrides or {}
    resolved_target = target_engine or recommendation.get("selected_engine")
    checks = [
        {"name": "recommendation_status", "passed": recommendation.get("status") == "RECOMMENDED", "detail": recommendation.get("status")},
        {"name": "target_engine_exists", "passed": bool(resolved_target), "detail": resolved_target},
        {"name": "target_engine_connected", "passed": bool(target_health.get("connected")), "detail": target_health},
        {"name": "no_estimated_measurements", "passed": recommendation.get("result", {}).get("evidence_provenance", {}).get("no_estimates_used") is True, "detail": recommendation.get("result", {}).get("evidence_provenance")},
        {"name": "override_keys_are_explicit", "passed": all(isinstance(key, str) and key for key in overrides), "detail": sorted(overrides)},
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "status": "passed" if passed else "blocked",
        "checks": checks,
        "current_engine": current_engine,
        "target_engine": resolved_target,
        "requested_overrides": overrides,
        "mutation_applied": False,
        "rollback_plan": "Restore the prior engine configuration and verify output correctness before resuming traffic.",
    }
