"""API contracts for controlled engine benchmark campaigns."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.benchmark.planner import BenchmarkCandidate


class BenchmarkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workload_id: str
    name: str | None = Field(default=None, max_length=255)
    candidates: list[BenchmarkCandidate] | None = None
    repetitions: int = Field(default=3, ge=1, le=10)
    warmup_runs: int = Field(default=1, ge=0, le=5)


class BenchmarkCampaignResponse(BaseModel):
    campaign_id: str
    name: str
    status: str
    workload_id: str
    plan: dict[str, Any]
    fairness_contract: dict[str, Any]
    error_message: str | None = None


class BenchmarkRunResponse(BaseModel):
    run_id: str
    engine: str
    repetition: int
    is_warmup: bool
    status: str
    configuration: dict[str, Any]
    metrics: dict[str, Any]
    resource_metrics: dict[str, Any]
    correctness: dict[str, Any]
    software_versions: dict[str, Any]
    error_message: str | None = None


class BenchmarkDetailResponse(BenchmarkCampaignResponse):
    runs: list[BenchmarkRunResponse]
    comparison: dict[str, Any]


class BenchmarkExecuteResponse(BaseModel):
    campaign_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
