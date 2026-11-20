"""Unified execution-engine contracts and adapters.

The package deliberately keeps engine-specific semantics behind adapters. A
caller can inspect capabilities and validate a pipeline without accidentally
falling back to a different engine.
"""

from app.engines.base import EngineAdapter, EngineCompatibilityError, EngineUnavailableError
from app.engines.registry import get_engine_adapter, list_engine_capabilities

__all__ = [
    "EngineAdapter",
    "EngineCompatibilityError",
    "EngineUnavailableError",
    "get_engine_adapter",
    "list_engine_capabilities",
]
