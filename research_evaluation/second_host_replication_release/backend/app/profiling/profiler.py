"""Bounded, explainable dataset profiling.

The profiler reads CSV/JSON in chunks and Parquet through row batches. It
never needs to materialize an entire unbounded input in backend memory. Each
reported statistic carries a scope (`exact`, `sampled`, or `estimated`).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq


class DatasetProfileError(ValueError):
    """Raised when a dataset cannot be safely profiled."""


ProgressCallback = Callable[[int, str], None]


def _looks_like_timestamp_name(name: str) -> bool:
    """Return whether a column name provides a meaningful time hint.

    Substring matching is intentionally avoided for short tokens: ``amount``
    contains ``time`` but is not a timestamp field.
    """
    normalized = name.strip().lower()
    if normalized in {"time", "date", "timestamp", "datetime"}:
        return True
    return bool(
        re.search(
            r"(?:^|[_ .-])(?:time|date|timestamp|datetime|created|updated)(?:$|[_ .-])",
            normalized,
        )
        or normalized.endswith(("_time", "_date", "_timestamp", "_datetime"))
    )


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy scalar values into JSON-safe primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if hasattr(value, "item"):
        return _json_value(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _dtype_label(series: pd.Series) -> str:
    dtype = str(series.dtype)
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "double"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp"
    return "string" if dtype == "object" or "string" in dtype else dtype


def _safe_sample(frame: pd.DataFrame, limit: int) -> pd.DataFrame:
    if len(frame) <= limit:
        return frame
    return frame.head(limit).copy()


class DatasetProfiler:
    """Profile one local dataset using bounded reads."""

    SUPPORTED_FORMATS = {"csv", "json", "jsonl", "ndjson", "parquet"}

    def __init__(self, *, max_json_array_bytes: int = 64 * 1024 * 1024) -> None:
        self.max_json_array_bytes = max_json_array_bytes

    def profile(
        self,
        source_uri: str,
        *,
        sample_rows: int = 10_000,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        path = self._resolve_local_path(source_uri)
        sample_rows = max(1, min(int(sample_rows), 100_000))
        self._progress(on_progress, 2, "discovered")
        fmt = self._detect_format(path)
        file_size = path.stat().st_size if path.is_file() else self._directory_size(path)
        file_hash = self._sha256(path) if path.is_file() else None
        self._progress(on_progress, 5, f"reading {fmt}")

        if fmt == "csv":
            result = self._profile_csv(path, sample_rows, on_progress)
        elif fmt in {"json", "jsonl", "ndjson"}:
            result = self._profile_json(path, fmt, sample_rows, on_progress)
        elif fmt == "parquet":
            result = self._profile_parquet(path, sample_rows, on_progress)
        else:  # pragma: no cover - guarded by _detect_format
            raise DatasetProfileError(f"Unsupported dataset format: {fmt}")

        result["dataset"] = {
            "source_uri": source_uri,
            "path": str(path),
            "format": fmt,
            "file_size_bytes": file_size,
            "sha256": file_hash,
            "sample_rows": sample_rows,
        }
        record_count = result.get("record_count", {}).get("value")
        if isinstance(record_count, (int, float)) and record_count > 0:
            result["dataset"]["estimated_record_size_bytes"] = round(file_size / record_count, 2)
        result["profile_metadata"] = {
            "profiler_version": "1.0",
            "generated_scope": "local_bounded_scan",
            "statistics_scope": result.get("statistics_scope", {}),
        }
        self._progress(on_progress, 100, "completed")
        return result

    @staticmethod
    def _progress(callback: ProgressCallback | None, percent: int, message: str) -> None:
        if callback:
            callback(max(0, min(100, percent)), message)

    @staticmethod
    def _resolve_local_path(source_uri: str) -> Path:
        if "://" in source_uri:
            raise DatasetProfileError(
                "Only local dataset paths are supported by this profiler; HDFS profiling requires a storage adapter."
            )
        path = Path(source_uri).expanduser().resolve()
        if not path.exists():
            raise DatasetProfileError(f"Dataset path does not exist: {source_uri}")
        if not path.is_file() and not path.is_dir():
            raise DatasetProfileError(f"Dataset path is not a file or directory: {source_uri}")
        return path

    @classmethod
    def _detect_format(cls, path: Path) -> str:
        suffix = path.suffix.lower().lstrip(".")
        if path.is_dir():
            suffixes = {p.suffix.lower().lstrip(".") for p in path.rglob("*") if p.is_file()}
            if "parquet" in suffixes:
                return "parquet"
        if suffix in cls.SUPPORTED_FORMATS:
            return suffix
        raise DatasetProfileError(
            f"Unsupported dataset extension '.{suffix}'. Supported formats: {sorted(cls.SUPPORTED_FORMATS)}"
        )

    @staticmethod
    def _directory_size(path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _profile_csv(self, path: Path, sample_rows: int, callback: ProgressCallback | None) -> dict[str, Any]:
        chunks: list[pd.DataFrame] = []
        total_rows = 0
        null_counts: Counter[str] = Counter()
        columns: list[str] = []
        total_bytes = max(path.stat().st_size, 1)
        try:
            for chunk in pd.read_csv(path, chunksize=10_000):
                if not columns:
                    columns = [str(column) for column in chunk.columns]
                total_rows += len(chunk)
                null_counts.update({str(k): int(v) for k, v in chunk.isna().sum().items()})
                remaining = sample_rows - sum(len(item) for item in chunks)
                if remaining > 0:
                    chunks.append(chunk.head(remaining).copy())
                self._progress(callback, 5 + int(min(path.stat().st_size, total_rows * max(1, path.stat().st_size // max(total_rows, 1))) / total_bytes * 75), "scanning csv")
        except Exception as exc:
            raise DatasetProfileError(f"CSV profiling failed: {exc}") from exc
        sample = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=columns)
        return self._summarize(
            sample,
            record_count={"value": total_rows, "scope": "exact"},
            null_counts=dict(null_counts),
            null_scope="exact",
            sample_scope="sampled" if total_rows > len(sample) else "exact",
            partition_characteristics={"partition_count": None, "scope": "not_applicable"},
        )

    def _profile_json(self, path: Path, fmt: str, sample_rows: int, callback: ProgressCallback | None) -> dict[str, Any]:
        if fmt == "json" and path.stat().st_size <= self.max_json_array_bytes:
            try:
                frame = pd.read_json(path)
            except ValueError:
                frame = pd.read_json(path, lines=True)
            sample = _safe_sample(frame, sample_rows)
            self._progress(callback, 85, "scanned json")
            return self._summarize(
                sample,
                record_count={"value": int(len(frame)), "scope": "exact"},
                null_counts={str(k): int(v) for k, v in frame.isna().sum().items()},
                null_scope="exact",
                sample_scope="sampled" if len(frame) > len(sample) else "exact",
                partition_characteristics={"partition_count": None, "scope": "not_applicable"},
            )
        if fmt == "json" and path.stat().st_size > self.max_json_array_bytes:
            raise DatasetProfileError(
                "Large JSON arrays are not loaded into backend memory; convert the dataset to JSON Lines or Parquet."
            )
        chunks: list[pd.DataFrame] = []
        total_rows = 0
        null_counts: Counter[str] = Counter()
        try:
            reader = pd.read_json(path, lines=True, chunksize=10_000)
            for chunk in reader:
                total_rows += len(chunk)
                null_counts.update({str(k): int(v) for k, v in chunk.isna().sum().items()})
                remaining = sample_rows - sum(len(item) for item in chunks)
                if remaining > 0:
                    chunks.append(chunk.head(remaining).copy())
            self._progress(callback, 85, "scanned json lines")
        except Exception as exc:
            raise DatasetProfileError(f"JSON Lines profiling failed: {exc}") from exc
        sample = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        return self._summarize(
            sample,
            record_count={"value": total_rows, "scope": "exact"},
            null_counts=dict(null_counts),
            null_scope="exact",
            sample_scope="sampled" if total_rows > len(sample) else "exact",
            partition_characteristics={"partition_count": None, "scope": "not_applicable"},
        )

    def _profile_parquet(self, path: Path, sample_rows: int, callback: ProgressCallback | None) -> dict[str, Any]:
        files = [path] if path.is_file() else sorted(path.rglob("*.parquet"))
        if not files:
            raise DatasetProfileError("No Parquet files found in dataset path.")
        total_rows = 0
        row_groups = 0
        sample_frames: list[pd.DataFrame] = []
        for index, file in enumerate(files):
            parquet = pq.ParquetFile(file)
            total_rows += parquet.metadata.num_rows
            row_groups += parquet.num_row_groups
            remaining = sample_rows - sum(len(frame) for frame in sample_frames)
            if remaining > 0:
                batch = next(parquet.iter_batches(batch_size=min(remaining, 10_000)), None)
                if batch is not None:
                    sample_frames.append(batch.to_pandas().head(remaining))
            self._progress(callback, 10 + int((index + 1) / len(files) * 75), "scanning parquet")
        sample = pd.concat(sample_frames, ignore_index=True) if sample_frames else pd.DataFrame()
        return self._summarize(
            sample,
            record_count={"value": int(total_rows), "scope": "exact"},
            null_counts={str(k): int(v) for k, v in sample.isna().sum().items()},
            null_scope="sampled",
            sample_scope="sampled" if total_rows > len(sample) else "exact",
            partition_characteristics={
                "file_count": len(files),
                "row_group_count": row_groups,
                "scope": "exact",
            },
        )

    def _summarize(
        self,
        sample: pd.DataFrame,
        *,
        record_count: dict[str, Any],
        null_counts: dict[str, int],
        null_scope: str,
        sample_scope: str,
        partition_characteristics: dict[str, Any],
    ) -> dict[str, Any]:
        total = int(record_count["value"] or 0)
        columns: list[dict[str, Any]] = []
        timestamp_fields: list[str] = []
        quality_issues: list[str] = []
        numeric_columns: list[str] = []
        for name in [str(column) for column in sample.columns]:
            series = sample[name]
            dtype = _dtype_label(series)
            null_count = int(null_counts.get(name, int(series.isna().sum())))
            null_pct = round((null_count / total) * 100, 4) if total else 0.0
            non_null = series.dropna()
            distinct = int(non_null.nunique(dropna=True))
            cardinality_scope = sample_scope
            stats: dict[str, Any] = {}
            if pd.api.types.is_numeric_dtype(series):
                numeric_columns.append(name)
                stats = {
                    "min": _json_value(non_null.min()) if len(non_null) else None,
                    "max": _json_value(non_null.max()) if len(non_null) else None,
                    "mean": _json_value(non_null.mean()) if len(non_null) else None,
                    "std": _json_value(non_null.std()) if len(non_null) > 1 else None,
                    "quantiles": {
                        "p25": _json_value(non_null.quantile(0.25)) if len(non_null) else None,
                        "p50": _json_value(non_null.quantile(0.5)) if len(non_null) else None,
                        "p75": _json_value(non_null.quantile(0.75)) if len(non_null) else None,
                    },
                }
            else:
                counts = non_null.astype(str).value_counts().head(5).to_dict()
                stats = {"top_values": [{"value": str(k), "count": int(v)} for k, v in counts.items()]}
            timestamp_score = 0.0
            timestamp_name_hint = _looks_like_timestamp_name(name)
            if timestamp_name_hint:
                timestamp_score = 0.5
            if len(non_null) and (
                not pd.api.types.is_numeric_dtype(series)
                or timestamp_name_hint
            ):
                parsed = pd.to_datetime(non_null, errors="coerce", utc=True)
                timestamp_score = max(timestamp_score, float(parsed.notna().mean()))
            is_timestamp = timestamp_score >= 0.8
            if is_timestamp:
                timestamp_fields.append(name)
            if null_pct >= 20:
                quality_issues.append(f"Column '{name}' has {null_pct}% null values ({null_scope}).")
            columns.append({
                "name": name,
                "data_type": dtype,
                "null_count": null_count,
                "null_percentage": null_pct,
                "null_scope": null_scope,
                "distinct_values": distinct,
                "distinct_scope": cardinality_scope,
                "cardinality_ratio": round(distinct / max(len(non_null), 1), 4),
                "statistics": stats,
                "timestamp_candidate": is_timestamp,
                "timestamp_parse_ratio": round(timestamp_score, 4),
            })

        duplicate_count = int(sample.duplicated().sum()) if len(sample) else 0
        duplicate_ratio = round(duplicate_count / max(len(sample), 1), 4)
        if duplicate_ratio > 0:
            quality_issues.append(f"Sample contains {duplicate_count} duplicate rows ({sample_scope}).")
        memory_bytes = int(sample.memory_usage(deep=True).sum()) if len(sample) else 0
        skew: list[dict[str, Any]] = []
        for column in sample.columns:
            counts = sample[column].dropna().astype(str).value_counts()
            if len(counts):
                skew.append({
                    "column": str(column),
                    "top_value_ratio": round(float(counts.iloc[0] / max(counts.sum(), 1)), 4),
                    "scope": sample_scope,
                })
        return {
            "record_count": record_count,
            "column_count": {"value": len(columns), "scope": "exact"},
            "columns": columns,
            "duplicate_characteristics": {
                "duplicate_rows": duplicate_count,
                "duplicate_ratio": duplicate_ratio,
                "scope": sample_scope,
            },
            "memory_characteristics": {
                "sample_memory_bytes": memory_bytes,
                "estimated_full_memory_bytes": round(memory_bytes / max(len(sample), 1) * total) if total else 0,
                "scope": "estimated_from_sample",
            },
            "numeric_columns": numeric_columns,
            "timestamp_fields": timestamp_fields,
            "event_time_suitability": {
                "suitable": bool(timestamp_fields),
                "timestamp_fields": timestamp_fields,
                "scope": "sampled",
            },
            "data_skew": skew,
            "partition_characteristics": partition_characteristics,
            "data_quality": {
                "issues": quality_issues,
                "quality_issue_count": len(quality_issues),
            },
            "statistics_scope": {
                "record_count": record_count["scope"],
                "column_count": "exact",
                "columns": sample_scope,
                "null_percentages": null_scope,
                "numeric_distributions": sample_scope,
                "cardinality": sample_scope,
                "duplicates": sample_scope,
                "data_skew": sample_scope,
            },
        }
