"""Prevent source/consumption telemetry being mistaken for committed output."""
from app.pipeline.progress import RunProgressTracker


def test_input_count_is_not_output_count():
    tracker = RunProgressTracker()
    tracker.start("evidence-input", "fixture", mode="streaming")
    tracker.emit("evidence-input", "spark_progress", {"totalInputRows": 1000000})
    progress = tracker.get_progress("evidence-input")
    assert progress["spark"]["recordsIn"] == 1000000
    assert progress["spark"]["recordsOut"] is None


def test_zero_output_is_preserved_and_verification_requires_evidence():
    tracker = RunProgressTracker()
    tracker.start("evidence-zero", "fixture", mode="streaming")
    tracker.emit("evidence-zero", "spark_done", {"input_rows": 1000000, "output_rows": 0})
    tracker.emit("evidence-zero", "hdfs_done", {"rows": 0})
    progress = tracker.get_progress("evidence-zero")
    assert progress["spark"]["recordsOut"] == 0
    assert progress["hdfs"]["rowsWritten"] == 0
    assert progress["hdfs"]["verified"] is None
