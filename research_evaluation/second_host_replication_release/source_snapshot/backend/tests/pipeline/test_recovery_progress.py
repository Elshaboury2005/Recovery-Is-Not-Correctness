from app.pipeline.progress import RunProgressTracker


def test_timing_is_same_clock_and_separate_from_public_progress_schema():
    tracker = RunProgressTracker()
    tracker.start("run", "pipeline", mode="streaming")
    tracker.emit("run", "spark_start", {})
    tracker.emit("run", "run_success", {})
    evidence = tracker.get_timing_evidence("run")
    assert [e["name"] for e in evidence["events"]] == ["pipeline_start", "stage_start", "pipeline_terminal"]
    assert all(e["clock_id"] == evidence["clock_id"] for e in evidence["events"])
    assert evidence["events"][0]["upper"] <= evidence["events"][-1]["lower"]
    assert "timing_events" not in tracker.get_progress("run")


def test_duplicate_and_old_batch_callbacks_cannot_inflate_committed_counter():
    tracker = RunProgressTracker()
    tracker.start("run", "pipeline", mode="streaming")
    for batch, count in [(0, 0), (1, 20), (1, 20), (0, 0), (2, 30)]:
        tracker.emit("run", "stream_batch_committed", {"batch_id": batch, "total_input_rows": count})
    evidence = tracker.get_timing_evidence("run")
    assert evidence["counter"]["value"] == 30
    assert len([e for e in evidence["events"] if e["name"] == "stream_batch_committed"]) == 3
    tracker.finish("run")
    assert tracker.get_timing_evidence("run") is None
