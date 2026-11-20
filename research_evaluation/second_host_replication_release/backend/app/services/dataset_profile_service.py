"""Dataset profile job orchestration and persistence."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import SyncSessionLocal
from app.models.dataset_profile import DatasetProfile
from app.metrics import transformation_profile_events_total
from app.profiling.profiler import DatasetProfileError, DatasetProfiler

logger = logging.getLogger(__name__)


def allowed_profile_roots() -> list[Path]:
    settings = get_settings()
    raw = settings.DATASET_PROFILE_ALLOWED_ROOTS
    return [Path(item.strip()).expanduser().resolve() for item in raw.split(",") if item.strip()]


def validate_profile_source(source_uri: str) -> Path:
    if "://" in source_uri:
        raise DatasetProfileError("Only local dataset paths are currently supported by the profiling API.")
    path = Path(source_uri).expanduser().resolve()
    if not any(path == root or root in path.parents for root in allowed_profile_roots()):
        raise DatasetProfileError("Dataset path is outside the configured profiling roots.")
    if not path.exists():
        raise DatasetProfileError(f"Dataset path does not exist: {source_uri}")
    return path


def profile_row_to_dict(row: DatasetProfile) -> dict[str, Any]:
    return {
        "profile_id": str(row.id),
        "dataset_name": row.dataset_name,
        "source_uri": row.source_uri,
        "status": row.status,
        "progress": row.progress,
        "format": row.format,
        "profile_version": row.profile_version,
        "result": row.result,
        "error_message": row.error_message,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def _set_job_state(db: Session, profile_id: uuid.UUID, **values: Any) -> None:
    row = db.get(DatasetProfile, profile_id)
    if row is None:
        return
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()


def run_profile_job(profile_id: str, source_uri: str, sample_rows: int) -> None:
    """Execute a profile in a worker thread using a durable synchronous session."""
    profile_uuid = uuid.UUID(profile_id)
    with SyncSessionLocal() as db:
        row = db.get(DatasetProfile, profile_uuid)
        if row is None:
            logger.error("Profile job %s disappeared before execution", profile_id)
            return
        row.status = "running"
        row.progress = 1
        row.started_at = datetime.now(timezone.utc)
        row.error_message = None
        db.commit()

        def on_progress(progress: int, _message: str) -> None:
            _set_job_state(db, profile_uuid, progress=progress)

        try:
            result = DatasetProfiler(
                max_json_array_bytes=get_settings().DATASET_PROFILE_MAX_JSON_ARRAY_BYTES
            ).profile(source_uri, sample_rows=sample_rows, on_progress=on_progress)
            row = db.get(DatasetProfile, profile_uuid)
            if row is not None:
                row.status = "succeeded"
                row.progress = 100
                row.format = result.get("dataset", {}).get("format")
                row.result = result
                row.finished_at = datetime.now(timezone.utc)
                db.commit()
                transformation_profile_events_total.labels(
                    format=str(row.format or "unknown"), status="succeeded"
                ).inc()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Dataset profiling job %s failed", profile_id)
            row = db.get(DatasetProfile, profile_uuid)
            if row is not None:
                row.status = "failed"
                row.error_message = str(exc)[:8000]
                row.finished_at = datetime.now(timezone.utc)
                db.commit()
                transformation_profile_events_total.labels(
                    format=str(row.format or "unknown"), status="failed"
                ).inc()


def compare_profiles(left: DatasetProfile, right: DatasetProfile) -> list[dict[str, Any]]:
    """Return explicit, machine-readable changes between two profile versions."""
    left_result = left.result or {}
    right_result = right.result or {}
    changes: list[dict[str, Any]] = []
    left_count = left_result.get("record_count", {}).get("value")
    right_count = right_result.get("record_count", {}).get("value")
    if left_count != right_count:
        changes.append({"field": "record_count", "before": left_count, "after": right_count})
    left_columns = {item.get("name"): item for item in left_result.get("columns", [])}
    right_columns = {item.get("name"): item for item in right_result.get("columns", [])}
    for name in sorted(set(left_columns) | set(right_columns)):
        if name not in left_columns:
            changes.append({"field": "columns", "column": name, "change": "added"})
        elif name not in right_columns:
            changes.append({"field": "columns", "column": name, "change": "removed"})
        elif left_columns[name] != right_columns[name]:
            changes.append({"field": "column", "column": name, "change": "modified"})
    return changes
