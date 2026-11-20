"""API contracts for safe reconfiguration lifecycle operations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReconfigurationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str
    current_engine: str | None = None
    target_engine: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class ReconfigurationResponse(BaseModel):
    operation_id: str
    recommendation_id: str
    current_engine: str | None
    target_engine: str
    state: str
    requested_overrides: dict[str, Any]
    preflight_evidence: dict[str, Any]
    audit_events: list[dict[str, Any]]
    execution_result: dict[str, Any]
    error_message: str | None


class ReconfigurationStateResponse(BaseModel):
    operation_id: str
    state: Literal["proposed", "preflight_passed", "approved", "executing", "succeeded", "failed", "blocked", "rolled_back"]
