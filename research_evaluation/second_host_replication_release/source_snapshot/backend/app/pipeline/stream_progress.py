"""
backend/app/pipeline/stream_progress.py
-----------------------------------------
Parsers and state tracking for PySpark Structured Streaming jobs.

Extracts structured progress lines emitted by ``streaming_processing_job.py``:
- STREAM_STARTED: {"query_id": "...", "run_id": "..."}
- STREAM_PROGRESS: {"batchId": 0, "numInputRows": 50, ...}
- SPARK_JOB_RESULT: {"input_rows": N, "output_rows": N, ...}

Also provides consumer lag calculation across partitions and a
``StreamingCompletionDetector`` for finite stream completion.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any


def wait_for_stream_start(started, stop_events, deadline, *, clock=time.monotonic):
    """Wait within the configured stream deadline, including cold query startup."""
    while True:
        if any(event.is_set() for event in stop_events) or clock() >= deadline:
            return False
        if started.is_set():
            return True
        started.wait(timeout=min(0.1, max(0.0, deadline-clock())))


logger = logging.getLogger(__name__)

STREAM_STARTED_PREFIX = "STREAM_STARTED:"
STREAM_PROGRESS_PREFIX = "STREAM_PROGRESS:"
SPARK_JOB_RESULT_PREFIX = "SPARK_JOB_RESULT:"


def parse_stream_started_line(line: str) -> dict[str, Any] | None:
    """Parse a STREAM_STARTED line into a dictionary, or return None."""
    line = line.strip()
    if not line.startswith(STREAM_STARTED_PREFIX):
        return None
    raw = line[len(STREAM_STARTED_PREFIX):].strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("Malformed STREAM_STARTED line: %s (%s)", line, exc)
        return None


def parse_stream_progress_line(line: str) -> dict[str, Any] | None:
    """Parse a STREAM_PROGRESS line into a dictionary, or return None."""
    line = line.strip()
    if not line.startswith(STREAM_PROGRESS_PREFIX):
        return None
    raw = line[len(STREAM_PROGRESS_PREFIX):].strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("Malformed STREAM_PROGRESS line: %s (%s)", line, exc)
        return None


def extract_spark_offset_sum(offset_obj: Any) -> int:
    """
    Sum offsets from a Spark endOffset JSON structure or integer.

    Spark Structured Streaming offsets can be:
    - An integer
    - A dict mapping partition strings/ints to integer offsets: {"0": 100, "1": 200}
    - A dict mapping topic to partition dict: {"topic": {"0": 100, "1": 200}}
    """
    if offset_obj is None:
        return 0
    if isinstance(offset_obj, (int, float)):
        return int(offset_obj)
    if isinstance(offset_obj, str):
        try:
            parsed = json.loads(offset_obj)
            return extract_spark_offset_sum(parsed)
        except Exception:
            try:
                return int(offset_obj)
            except ValueError:
                return 0
    if isinstance(offset_obj, dict):
        total = 0
        for val in offset_obj.values():
            if isinstance(val, (int, float)):
                total += int(val)
            elif isinstance(val, (dict, list, str)):
                total += extract_spark_offset_sum(val)
        return total
    return 0


def compute_lag(
    end_offsets: dict[int, int] | int | None,
    spark_consumed_offset: Any,
) -> int | None:
    """
    Compute lag per partition. Missing/malformed observations are unknown.

    Parameters
    ----------
    end_offsets : dict[int, int] | int | None
        Topic end offsets (high watermarks) from Kafka Admin / consumer.
    spark_consumed_offset : Any
        Spark's current consumed endOffset from StreamingQueryProgress.

    Returns
    -------
    int | None
        Non-negative lag, or None when both positions cannot be compared.
    """
    def positions(value: Any) -> dict[str, int] | None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return None
        if type(value) is int and value >= 0:
            return {"scalar": value}
        if not isinstance(value, dict) or not value:
            return None
        # The executor subscribes to exactly one topic.
        if len(value) == 1 and isinstance(next(iter(value.values())), dict):
            value = next(iter(value.values()))
        if not value or any(type(v) is not int or v < 0 for v in value.values()):
            return None
        return {str(k): v for k, v in value.items()}

    ends, consumed = positions(end_offsets), positions(spark_consumed_offset)
    if ends is None or consumed is None or ends.keys() != consumed.keys():
        return None
    return sum(max(0, end - consumed[p]) for p, end in ends.items())


class StreamingCompletionDetector:
    """
    Detects finite stream completion based on producer finish, consumer lag, and idle timeout.

    A stream is considered complete when:
    1. Producer has completed (expected_total_rows is provided) and spark has processed
       at least expected_total_rows and consumer lag is 0; OR
    2. Consumer lag is 0 and no new rows have been processed for ``idle_timeout_seconds``; OR
    3. ``max_runtime_seconds`` hard cap is exceeded.
    """

    def __init__(
        self,
        idle_timeout_seconds: float = 20.0,
        max_runtime_seconds: float = 600.0,
    ) -> None:
        self.idle_timeout_seconds = float(idle_timeout_seconds)
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.start_time = time.monotonic()
        self.last_activity_time = time.monotonic()
        self.last_total_rows = 0

    def record_activity(self, current_total_rows: int, current_lag: int | None) -> None:
        """Update last activity timestamp if new rows arrived or lag > 0."""
        now = time.monotonic()
        if current_total_rows > self.last_total_rows or current_lag is None or current_lag > 0:
            self.last_activity_time = now
            self.last_total_rows = current_total_rows

    def is_complete(
        self,
        current_lag: int | None,
        current_total_rows: int,
        expected_total_rows: int | None = None,
        producer_done: bool = False,
    ) -> bool:
        """
        Check if the streaming query has processed all available records and drained.
        """
        now = time.monotonic()
        self.record_activity(current_total_rows, current_lag)

        # A stream cannot be drained if an expected total is defined and producer is still active
        if expected_total_rows is not None and not producer_done:
            return False

        # Condition 1: Known producer total reached and lag is zero
        if expected_total_rows is not None:
            if producer_done and current_total_rows >= expected_total_rows and current_lag == 0:
                logger.info(
                    "Streaming completion: expected rows (%d) reached with lag 0",
                    expected_total_rows,
                )
                return True
            # An idle interval must never excuse missing expected input rows.
            return False

        # Condition 2: Lag is 0 and idle for idle_timeout_seconds after producer is done
        idle_time = now - self.last_activity_time
        if current_lag == 0 and idle_time >= self.idle_timeout_seconds:
            logger.info(
                "Streaming completion: idle for %.1fs (threshold %.1fs) with lag 0",
                idle_time,
                self.idle_timeout_seconds,
            )
            return True

        return False

    def is_timed_out(self) -> bool:
        """Check if max runtime hard cap has been exceeded."""
        elapsed = time.monotonic() - self.start_time
        if elapsed >= self.max_runtime_seconds:
            logger.warning(
                "Streaming job reached max runtime limit: %.1fs >= %.1fs",
                elapsed,
                self.max_runtime_seconds,
            )
            return True
        return False
