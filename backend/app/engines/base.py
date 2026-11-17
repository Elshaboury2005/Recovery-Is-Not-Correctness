"""Abstract execution-engine adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from app.engines.models import (
    EngineCapability,
    EngineExecutionPlan,
    EngineJobHandle,
    EngineJobStatus,
    EngineValidationResult,
)
from app.pipeline.config_models import PipelineConfig


class EngineUnavailableError(RuntimeError):
    """Raised when an optional engine cannot be reached or is not enabled."""


class EngineCompatibilityError(ValueError):
    """Raised when a pipeline asks an engine to do unsupported work."""


class EngineAdapter(ABC):
    """Common adapter surface; implementations retain engine-specific behavior."""

    name: str

    @abstractmethod
    def capability(self) -> EngineCapability:
        """Return conservative static capabilities."""

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return a real service health result without raising for network errors."""

    @abstractmethod
    async def validate_pipeline(self, config: PipelineConfig) -> EngineValidationResult:
        """Validate engine compatibility before data is read or a job is submitted."""

    @abstractmethod
    def generate_plan(
        self,
        config: PipelineConfig,
        *,
        input_source: str | None = None,
        output_path: str | None = None,
        artifact_path: str | None = None,
    ) -> EngineExecutionPlan:
        """Generate an engine-specific plan from a validated logical pipeline."""

    @abstractmethod
    async def submit(
        self,
        plan: EngineExecutionPlan,
        *,
        run_id: str | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> EngineJobHandle:
        """Submit a real job or raise an explicit compatibility/availability error."""

    @abstractmethod
    async def get_status(self, job_id: str) -> EngineJobStatus:
        """Return normalized job state."""

    @abstractmethod
    async def get_metrics(self, job_id: str) -> dict[str, Any]:
        """Read engine metrics; missing measurements remain explicit."""

    @abstractmethod
    async def get_logs(self, job_id: str) -> list[str]:
        """Retrieve available engine logs."""

    @abstractmethod
    async def cancel(self, job_id: str) -> EngineJobStatus:
        """Cancel a job when the engine supports it."""

    @abstractmethod
    async def checkpoint_info(self, job_id: str) -> dict[str, Any]:
        """Return checkpoint evidence or an explicit unsupported result."""
