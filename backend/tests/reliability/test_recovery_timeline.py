"""Adversarial measurement contracts, independent of Docker and wall clocks."""
from copy import deepcopy
import math
import threading
import time
from unittest.mock import Mock, patch

import pytest

from app.reliability.recovery_timeline import RecoveryTimeline, elapsed_interval, sustained_recovery
from app.reliability.recovery_observer import RecoveryObserver


def event(lower, upper=None, **extra):
    return {"lower": lower, "upper": lower if upper is None else upper, "clock_id": "test", **extra}


def samples(stop=60, rate=10, **extra):
    return [event(t, value=rate*t, **extra) for t in range(stop+1)]


@pytest.mark.parametrize("start,end,status,lo,hi", [
    (event(1), event(4), "exact", 3, 3),
    (event(1, 2), event(4, 6), "interval", 2, 5),
    (event(1, 4), event(3, 6), "interval", 0, 5),
    (event(4), event(1), "unobservable", None, None),
    (event(1), event(4, clock_id="other"), "unobservable", None, None),
    (event(None, 1), event(4), "unobservable", None, None),
    (None, event(4), "unobservable", None, None),
    (event(1), None, "unobservable", None, None),
    (event(1), event(math.nan), "unobservable", None, None),
    (event(1), event(6, 4), "unobservable", None, None),
])
def test_elapsed_bounds(start, end, status, lo, hi):
    result = elapsed_interval(start, end)
    assert (result["status"], result["lower_seconds"], result["upper_seconds"]) == (status, lo, hi)


def test_censoring_requires_explicit_observation_horizon():
    result = elapsed_interval(event(1, 2), None, censor_at=10)
    assert result["status"] == "right_censored"
    assert result["lower_seconds"] == 8 and result["upper_seconds"] is None
    assert elapsed_interval(event(1, 2), None, censor_at=0)["status"] == "unobservable"


def test_unknown_probe_widens_transition_without_becoming_downtime():
    timeline = RecoveryTimeline(clock_id="test", monotonic=lambda: 1.5)
    timeline.state("service", True, lower=0, upper=1, source="probe")
    timeline.mark("fault_dispatch")
    timeline.state("service", None, lower=2, upper=3, source="probe")
    assert [e["name"] for e in timeline.events] == ["fault_dispatch"]
    timeline.state("service", False, lower=4, upper=5, source="probe")
    timeline.state("service", None, lower=6, upper=7, source="probe")
    timeline.state("service", True, lower=8, upper=9, source="probe")
    result = timeline.summary()["metrics"]["service_readiness_recovery"]
    assert result["lower_seconds"] == 2.5 and result["upper_seconds"] == 7.5
    assert result["end_event"]["lower"] == 4


def test_preexisting_recovery_cannot_satisfy_later_fault():
    timeline = RecoveryTimeline(clock_id="test")
    for value, t in [(True, 0), (False, 1), (True, 2)]:
        timeline.state("service", value, lower=t, upper=t, source="probe")
    timeline.mark("fault_dispatch", lower=3, upper=3)
    assert timeline.summary()["metrics"]["service_readiness_recovery"]["status"] == "unobservable"
    for value, t in [(False, 4), (True, 5)]:
        timeline.state("service", value, lower=t, upper=t, source="probe")
    result = timeline.summary()["metrics"]["service_readiness_recovery"]
    assert result["end_event"]["upper"] == 5
    assert len([e for e in timeline.events if e["name"] == "service_restored"]) == 2


def test_always_healthy_does_not_prove_recovery():
    timeline = RecoveryTimeline(clock_id="test")
    timeline.mark("fault_dispatch", lower=1, upper=1)
    for t in (0, 2, 3):
        timeline.state("infrastructure", True, lower=t, upper=t, source="probe")
    assert timeline.summary()["metrics"]["infrastructure_recovery"]["status"] == "unobservable"


def test_initial_down_is_left_unbounded_not_zero_duration():
    timeline = RecoveryTimeline(clock_id="test")
    timeline.mark("fault_dispatch", lower=0, upper=0)
    timeline.state("infrastructure", False, lower=1, upper=1, source="probe")
    timeline.state("infrastructure", True, lower=4, upper=4, source="probe")
    assert timeline.summary()["metrics"]["confirmed_disruption_duration"]["status"] == "unobservable"


def test_snapshot_and_ingestion_do_not_alias_mutable_evidence():
    timeline = RecoveryTimeline(clock_id="test")
    source = event(1, name="pipeline_start", details={"nested": [1]})
    timeline.ingest(source)
    source["details"]["nested"].append(2)
    snapshot = timeline.summary()
    snapshot["events"][0]["details"]["nested"].append(3)
    assert timeline.events[0]["details"]["nested"] == [1]
    with pytest.raises(ValueError):
        timeline.ingest(event(2, name="pipeline_terminal", clock_id="other"))


def test_out_of_order_unknown_observations_are_rejected():
    timeline = RecoveryTimeline()
    timeline.state("service", None, lower=2, upper=4, source="probe")
    with pytest.raises(ValueError):
        timeline.state("service", True, lower=3, upper=5, source="probe")
    with pytest.raises(ValueError):
        timeline.state("service", 1, lower=6, upper=7, source="probe")


def test_sustained_recovery_requires_three_full_windows():
    result = sustained_recovery(samples(30), baseline_rate=10, after=0)
    assert result["status"] == "observed"
    assert result["event"]["lower"] == 0
    assert result["event"]["confirmed_at"] == 30
    assert len(result["windows"]) == 3
    assert sustained_recovery(samples(29), baseline_rate=10, after=0)["event"] is None


def test_transient_spike_is_not_sustained_recovery():
    data = samples(45)
    for sample in data:
        sample["value"] = 1000 if sample["lower"] >= 10 else 0
    result = sustained_recovery(data, baseline_rate=10, after=0)
    assert result["event"] is None and result["status"] == "right_censored"


@pytest.mark.parametrize("disruption", ["unknown", "reset", "gap", "clock", "epoch"])
def test_coverage_break_resets_sustained_window(disruption):
    data = samples(50, epoch="original")
    if disruption == "unknown":
        data[20]["value"] = None
    elif disruption == "reset":
        for s in data[20:]:
            s["value"] -= 200
    elif disruption == "gap":
        data = data[:16]+data[20:]
    elif disruption == "clock":
        for s in data[20:]:
            s["clock_id"] = "restarted"
    elif disruption == "epoch":
        for s in data[20:]:
            s["epoch"] = "restarted"
    result = sustained_recovery(data[:-1], baseline_rate=10, after=0)
    assert result["event"] is None
    assert result["status"] == "unobservable"


@pytest.mark.parametrize("baseline", [None, 0, -1, math.nan, math.inf, True])
def test_absent_or_invalid_baseline_never_becomes_zero_recovery(baseline):
    assert sustained_recovery(samples(), baseline_rate=baseline, after=0)["status"] == "unobservable"


def test_probe_uncertainty_reduces_rate_lower_bound():
    data = [event(t, t+0.2, value=10*t) for t in range(40)]
    result = sustained_recovery(data, baseline_rate=10, fraction=1, after=0)
    assert result["event"] is None
    assert all(w["rate_lower"] < 10 for w in result["windows"])


def test_observer_captures_disruption_during_blocking_fault_call():
    state = {"value": True}
    observed_down = threading.Event()
    def probe():
        if state["value"] is False:
            observed_down.set()
        return {"value": state["value"], "source": "controlled real thread"}
    observer = RecoveryObserver({"infrastructure": probe}, interval=0.005)
    assert observer.start()
    observer.timeline.mark("fault_dispatch")
    state["value"] = False
    assert observed_down.wait(1)
    state["value"] = True
    deadline = time.monotonic()+1
    while not any(e["name"] == "infrastructure_restored" for e in observer.timeline.summary()["events"]):
        assert time.monotonic() < deadline
        time.sleep(0.005)
    evidence = observer.stop()
    assert evidence["metrics"]["infrastructure_recovery"]["status"] == "interval"
    assert evidence["observer"]["threads_stopped"] is True


def test_probe_error_is_unknown_and_does_not_create_loss():
    observer = RecoveryObserver({"service": Mock(side_effect=TimeoutError)}, interval=0.01)
    observer.start()
    evidence = observer.stop()
    assert evidence["observations"][0]["value"] is None
    assert not any(e["name"] == "service_lost" for e in evidence["events"])


def test_stuck_probe_is_explicit_and_cannot_mutate_closed_evidence():
    unblock = threading.Event()
    observer = RecoveryObserver({"service": lambda: (unblock.wait(2) or {"value": True})}, interval=0.01)
    assert observer.start(timeout=0.01) is False
    evidence = observer.stop(timeout=0.01)
    assert evidence["observer"]["threads_stopped"] is False
    unblock.set()
    observer._threads[0].join(1)
    assert observer.stop()["observations"] == evidence["observations"] == []


def test_application_recovery_requires_a_new_increment_after_readiness():
    timeline = RecoveryTimeline(clock_id="test")
    observer = RecoveryObserver({}, timeline=timeline)
    timeline.mark("fault_dispatch", lower=1, upper=1)
    for value, t in [(True, 0), (False, 2), (True, 4)]:
        timeline.state("service", value, lower=t, upper=t, source="probe")
    def observe(t, value, epoch="run"):
        observer._pipeline({"clock_id": "test", "counter": {"value": value,
            "epoch": epoch, "stage": "input", "committed": True}}, t, t)
    observe(3, 100)
    observe(5, 200)  # Delta straddles readiness; not accepted.
    assert not observer._progress_recorded
    observe(6, 200)  # Stale progress; not accepted.
    assert not observer._progress_recorded
    observe(7, 5, epoch="new")  # Reset/replay epoch; not accepted.
    assert not observer._progress_recorded
    observe(8, 15, epoch="new")
    result = observer.stop()["metrics"]
    assert result["application_progress_recovery"]["lower_seconds"] == 6
    assert result["committed_progress_recovery"]["upper_seconds"] == 7
    assert result["sustained_throughput_recovery"]["status"] == "unobservable"


def test_production_validation_is_not_independent_validation():
    timeline = RecoveryTimeline(clock_id="test")
    timeline.ingest(event(1, name="pipeline_start"))
    timeline.ingest(event(4, name="validation_complete"))
    metrics = timeline.summary()["metrics"]
    assert metrics["production_validation_completion"]["upper_seconds"] == 3
    assert metrics["validated_output_completion"]["status"] == "unobservable"
