import threading

from app.pipeline.stream_progress import wait_for_stream_start


class SimulatedStart:
    def __init__(self, time_source, start_at):
        self.time_source = time_source
        self.start_at = start_at

    def is_set(self):
        return self.time_source[0] >= self.start_at

    def wait(self, timeout):
        self.time_source[0] += timeout


def test_cold_start_after_30_seconds_is_allowed_within_configured_runtime():
    now = [0.0]
    assert wait_for_stream_start(SimulatedStart(now, 42), (), 60, clock=lambda: now[0])
    assert 42 <= now[0] < 43


def test_startup_cannot_exceed_configured_deadline():
    now = [0.0]
    assert not wait_for_stream_start(SimulatedStart(now, 100), (), 10, clock=lambda: now[0])
    assert now[0] == 10


def test_cancelled_startup_never_publishes_even_if_start_event_is_set():
    now = [0.0]
    stop = threading.Event()
    stop.set()
    assert not wait_for_stream_start(SimulatedStart(now, 0), (stop,), 60, clock=lambda: now[0])
