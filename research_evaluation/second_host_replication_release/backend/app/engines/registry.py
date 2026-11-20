"""Engine adapter registry."""

from __future__ import annotations

from app.engines.base import EngineAdapter
from app.engines.capabilities import flink_capability, spark_capability
from app.engines.flink import FlinkEngineAdapter
from app.engines.models import EngineName
from app.engines.spark import SparkEngineAdapter


def get_engine_adapter(engine: EngineName) -> EngineAdapter:
    if engine == "spark":
        return SparkEngineAdapter()
    if engine == "flink":
        return FlinkEngineAdapter()
    raise ValueError(f"Unsupported engine: {engine}")


def list_engine_capabilities() -> list[dict]:
    return [spark_capability().model_dump(), flink_capability().model_dump()]

