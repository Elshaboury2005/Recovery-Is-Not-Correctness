"""API contracts for dataset profiling."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_uri: str = Field(..., min_length=1, max_length=2048)
    dataset_name: str | None = Field(default=None, max_length=255)
    sample_rows: int = Field(default=10_000, ge=100, le=100_000)


class ProfileJobResponse(BaseModel):
    profile_id: str
    dataset_name: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: int


class ProfileResponse(ProfileJobResponse):
    source_uri: str
    format: str | None
    profile_version: int
    result: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ProfileComparisonResponse(BaseModel):
    left_profile_id: str
    right_profile_id: str
    changes: list[dict[str, Any]]
