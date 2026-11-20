"""Workload classification API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkloadClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline_yaml: str = Field(..., min_length=1)
    dataset_profile_id: str | None = None
    name: str | None = Field(default=None, max_length=255)
    constraints: dict[str, Any] = Field(default_factory=dict)


class WorkloadClassifyResponse(BaseModel):
    workload_id: str
    name: str
    classification: dict[str, Any]


class WorkloadResponse(BaseModel):
    workload_id: str
    name: str
    dataset_profile_id: str | None
    constraints: dict[str, Any] | None
    classification: dict[str, Any]
    created_at: datetime
