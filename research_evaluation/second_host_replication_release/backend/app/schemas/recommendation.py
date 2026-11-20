"""API contracts for architecture recommendations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RecommendationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workload_id: str
    benchmark_campaign_id: str | None = None
    optimization_goal: Literal["execution_time", "throughput", "latency", "resource_usage", "reliability", "balanced"] = "balanced"
    resource_constraints: dict[str, Any] = Field(default_factory=dict)


class RecommendationResponse(BaseModel):
    recommendation_id: str
    workload_id: str
    benchmark_campaign_id: str | None
    optimization_goal: str
    selected_engine: str | None
    status: str
    result: dict[str, Any]
