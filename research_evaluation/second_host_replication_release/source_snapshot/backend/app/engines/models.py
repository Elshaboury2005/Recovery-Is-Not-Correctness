"""Shared models for engine capability, planning, and job state."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EngineName = Literal["spark", "flink"]
EngineSelectionMode = Literal["manual", "automatic_recommendation", "verified_benchmark"]
JobMode = Literal["batch", "streaming"]
JobState = Literal["submitted", "running", "succeeded", "failed", "cancelled", "unknown"]


class EngineCapability(BaseModel):
    """A conservative, inspectable description of one engine adapter."""

    model_config = ConfigDict(extra="forbid")

    engine: EngineName
    version: str
    available: bool = False
    supports_batch: bool = True
    supports_streaming: bool = False
    supports_checkpoints: bool = False
    supports_cancellation: bool = False
    supported_sources: list[str] = Field(default_factory=list)
    supported_operations: list[str] = Field(default_factory=list)
    supported_storages: list[str] = Field(default_factory=list)
    recovery_signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class EngineValidationResult(BaseModel):
    """Result of validating a pipeline against one engine."""

    model_config = ConfigDict(extra="forbid")

    engine: EngineName
    compatible: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    capabilities: EngineCapability


class EngineExecutionPlan(BaseModel):
    """Engine-neutral plan with explicit input/output references."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    engine: EngineName
    pipeline_name: str
    pipeline_version: str
    mode: JobMode
    input_source: str | None = None
    output_path: str | None = None
    operations: list[dict[str, Any]] = Field(default_factory=list)
    pipeline_schema: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="schema",
    )
    engine_options: dict[str, Any] = Field(default_factory=dict)
    artifact_path: str | None = None


class EngineJobHandle(BaseModel):
    """Stable reference returned after a job is submitted."""

    model_config = ConfigDict(extra="forbid")

    engine: EngineName
    job_id: str
    state: JobState
    output_path: str | None = None
    checkpoint_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineJobStatus(BaseModel):
    """Normalized job state with raw engine evidence retained."""

    model_config = ConfigDict(extra="forbid")

    engine: EngineName
    job_id: str
    state: JobState
    raw_state: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
