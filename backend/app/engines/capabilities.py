"""Static capability declarations used before runtime service calls."""

from app.engines.models import EngineCapability


def spark_capability(*, available: bool = False, version: str = "3.5.0") -> EngineCapability:
    return EngineCapability(
        engine="spark",
        version=version,
        available=available,
        supports_batch=True,
        supports_streaming=True,
        supports_checkpoints=True,
        supports_cancellation=True,
        supported_sources=["csv", "json", "api", "kafka"],
        supported_operations=[
            "remove_nulls",
            "remove_duplicates",
            "filter",
            "select_columns",
            "rename_columns",
            "type_conversion",
            "aggregate",
        ],
        supported_storages=["hdfs", "local"],
        recovery_signals=["job_state", "stream_progress", "checkpoint_path", "hdfs_output"],
        limitations=["Spark checkpoints are not portable to Flink."],
    )


def flink_capability(*, available: bool = False, version: str = "1.20.1") -> EngineCapability:
    return EngineCapability(
        engine="flink",
        version=version,
        available=available,
        supports_batch=True,
        supports_streaming=True,
        supports_checkpoints=True,
        supports_cancellation=True,
        supported_sources=["kafka"],
        supported_operations=[
            "remove_nulls",
            "filter",
            "select_columns",
            "rename_columns",
            "type_conversion",
        ],
        supported_storages=["hdfs"],
        recovery_signals=["job_state", "checkpoint_status", "taskmanager_status"],
        limitations=[
            "The current adapter requires a verified Flink job artifact.",
            "Cross-engine checkpoint/state migration is not supported.",
            "Batch CSV/JSON source execution is not yet exposed by the adapter.",
        ],
    )
