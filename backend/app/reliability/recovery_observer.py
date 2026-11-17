"""Concurrent, read-only recovery observations, including blocking fault calls.

Each probe has its own thread so a service timeout cannot conceal a short
container restart. Probe request/response brackets are retained in full.
Neither successful monitoring nor container health establishes fault exposure
to an active workload; that is a separate experimental inclusion decision.
"""
from __future__ import annotations

import threading
import time

from app.reliability.recovery_timeline import RecoveryTimeline, bounded, finite, sustained_recovery


class DisabledRecoveryObserver:
    """Explicit observer-disabled mode for matched research controls.

    The coordinator still owns the timeline clock and fault markers, but no
    service/pipeline probes are started.  This keeps the control condition
    auditable without silently treating missing observations as recovery.
    """

    def __init__(self, *, timeline=None):
        self.timeline = timeline or RecoveryTimeline()
        self._started = False
        self._stopped = False

    def start(self, *, timeout=5.0):
        if self._started:
            raise RuntimeError("Observer cannot be restarted")
        self._started = True
        self.timeline.mark("observation_start", source="observer disabled; essential coordinator audit retained")
        return True

    def stop(self, *, timeout=3.0):
        if not self._stopped:
            self._stopped = True
            self.timeline.mark("observation_end", source="observer disabled; essential coordinator audit retained")
        evidence = self.timeline.summary()
        evidence["counter_samples"] = []
        evidence["observer"] = {
            "enabled": False,
            "interval_seconds": None,
            "all_probes_started": False,
            "threads_stopped": True,
            "errors": [],
            "missing_endpoint_policy": "unobservable; observer-disabled control",
        }
        evidence["throughput_rule"] = {
            "status": "unobservable",
            "reason": "Observer-disabled control has no pipeline probe",
            "event": None,
            "windows": [],
        }
        return evidence


class RecoveryObserver:
    def __init__(self, probes, *, timeline=None, interval=0.5, pipeline_probe=None,
                 baseline_rate=None, baseline_stage=None):
        if interval <= 0:
            raise ValueError("Observation interval must be positive")
        self.timeline = timeline or RecoveryTimeline()
        self.probes = dict(probes)
        if pipeline_probe is not None:
            self.probes["pipeline"] = pipeline_probe
        self.interval = interval
        self._stop = threading.Event()
        self._ready = {name: threading.Event() for name in self.probes}
        self._threads = []
        self._started = False
        self._closed = False
        self._errors = []
        self._lock = threading.Lock()
        self._seen_events = set()
        self._counter_samples = []
        self._previous_counter = None
        self._progress_recorded = False
        self.baseline_rate = baseline_rate
        self.baseline_stage = baseline_stage

    def start(self, *, timeout=5.0):
        if self._started:
            raise RuntimeError("Observer cannot be restarted")
        self._started = True
        self.timeline.mark("observation_start")
        for signal, probe in self.probes.items():
            thread = threading.Thread(target=self._loop, args=(signal, probe),
                                      name=f"recovery-{signal}", daemon=True)
            self._threads.append(thread)
            thread.start()
        deadline = time.monotonic() + timeout
        for ready in self._ready.values():
            ready.wait(max(0.0, deadline-time.monotonic()))
        return all(ready.is_set() for ready in self._ready.values())

    def _loop(self, signal, probe):
        while not self._stop.is_set():
            lower = self.timeline.clock()
            try:
                result = probe()
                if not isinstance(result, dict):
                    result = {"value": None, "source": signal, "error": "Invalid probe response"}
            except Exception as exc:
                result = {"value": None, "source": signal, "error": type(exc).__name__}
            upper = self.timeline.clock()
            with self._lock:
                if self._closed:
                    return
                try:
                    if signal == "pipeline":
                        self._pipeline(result, lower, upper)
                    else:
                        value = result.get("value")
                        if type(value) is not bool:
                            value = None
                        self.timeline.state(signal, value, lower=lower, upper=upper,
                                            source=result.get("source", signal),
                                            probe={k: v for k, v in result.items() if k != "value"})
                except Exception as exc:
                    self._errors.append({"signal": signal, "error": type(exc).__name__,
                                         "lower": lower, "upper": upper})
            self._ready[signal].set()
            self._stop.wait(self.interval)

    def _pipeline(self, result, lower, upper):
        for event in result.get("events", []):
            identity = (event.get("name"), event.get("lower"), event.get("clock_id"))
            if identity not in self._seen_events:
                self.timeline.ingest(event)
                self._seen_events.add(identity)
        counter = result.get("counter") or {}
        sample = {**counter, "lower": lower, "upper": upper, "clock_id": self.timeline.clock_id,
                  "wall_utc": self.timeline.wall()}
        if result.get("clock_id") != self.timeline.clock_id:
            sample["value"] = None
        self._counter_samples.append(sample)
        previous = self._previous_counter
        self._previous_counter = sample
        restoration = self.timeline.summary()["metrics"]["service_readiness_recovery"]["end_event"]
        if (self._progress_recorded or not bounded(restoration) or previous is None
                or not finite(previous.get("value")) or not finite(sample.get("value"))
                or previous["lower"] < restoration["upper"]
                or previous.get("epoch") != sample.get("epoch")
                or previous.get("stage") != sample.get("stage")
                or sample["value"] <= previous["value"]):
            return
        self.timeline.mark("application_progress", lower=previous["lower"], upper=upper,
                           source=counter.get("source", "pipeline counter"), stage=counter.get("stage"))
        if counter.get("committed") is True:
            self.timeline.mark("committed_progress", lower=previous["lower"], upper=upper,
                               source=counter.get("source", "pipeline counter"), stage=counter.get("stage"),
                               scope="completed query batch progress; independent output correctness is separate")
        self._progress_recorded = True

    def stop(self, *, timeout=3.0):
        self._stop.set()
        deadline = time.monotonic()+timeout
        for thread in self._threads:
            thread.join(max(0.0, deadline-time.monotonic()))
        with self._lock:
            if not self._closed:
                self._closed = True
                self.timeline.mark("observation_end")
            evidence = self.timeline.summary()
            restoration = evidence["metrics"]["service_readiness_recovery"]["end_event"]
            throughput = sustained_recovery(
                [{**s, "value": s.get("value") if s.get("stage") == self.baseline_stage else None}
                 for s in self._counter_samples],
                baseline_rate=self.baseline_rate,
                after=restoration["upper"] if bounded(restoration) else self.timeline.clock(),
            )
            if throughput["event"] and not any(e["name"] == "throughput_recovered" for e in evidence["events"]):
                self.timeline.ingest(throughput["event"])
                evidence = self.timeline.summary()
            evidence["throughput_rule"] = {"baseline_rate": self.baseline_rate,
                "baseline_stage": self.baseline_stage, "fraction": 0.9, "window_seconds": 10,
                "sustained_seconds": 30, "max_gap_seconds": 3, **throughput}
            evidence["counter_samples"] = list(self._counter_samples)
            evidence["observer"] = {
                "interval_seconds": self.interval,
                "all_probes_started": all(r.is_set() for r in self._ready.values()),
                "threads_stopped": all(not t.is_alive() for t in self._threads),
                "errors": list(self._errors),
                "missing_endpoint_policy": "unobservable; polling alone does not establish continuous absence",
            }
            return evidence
