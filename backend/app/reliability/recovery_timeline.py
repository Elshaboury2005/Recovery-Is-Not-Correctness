"""Versioned recovery evidence with one monotonic clock and interval estimates.

Polling observes transitions between observations; it does not establish an
exact failure instant. Unknown probes are retained and never converted to false.
This module performs no service calls and is also usable by the research runner.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import threading
import time
import uuid
from copy import deepcopy


# A process restart creates a new domain. Never subtract monotonic timestamps
# from different processes, even when their numerical values look compatible.
PROCESS_CLOCK_ID = str(uuid.uuid4())


METRICS = {
    'fault_dispatch_latency': ('fault_request', 'fault_dispatch'),
    'confirmed_disruption_duration': ('infrastructure_disrupted', 'infrastructure_restored'),
    'infrastructure_recovery': ('fault_dispatch', 'infrastructure_restored'),
    'service_readiness_recovery': ('fault_dispatch', 'service_restored'),
    'application_progress_recovery': ('fault_dispatch', 'application_progress'),
    'committed_progress_recovery': ('fault_dispatch', 'committed_progress'),
    'sustained_throughput_recovery': ('fault_dispatch', 'throughput_recovered'),
    'total_pipeline_duration': ('pipeline_start', 'pipeline_terminal'),
    'validated_output_completion': ('pipeline_start', 'independent_validation_complete'),
    'production_validation_completion': ('pipeline_start', 'validation_complete'),
    'rollback_to_service_readiness': ('rollback_start', 'service_restored'),
}


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def bounded(event):
    return (isinstance(event, dict) and finite(event.get('lower'))
            and finite(event.get('upper')) and event['lower'] <= event['upper']
            and bool(event.get('clock_id')))


def elapsed_interval(start, end, *, censor_at=None):
    """Conservative difference of event intervals; no midpoint is fabricated."""
    result = {'status': 'unobservable', 'lower_seconds': None, 'upper_seconds': None,
              'reason': None, 'start_event': start, 'end_event': end}
    if not bounded(start):
        return {**result, 'reason': 'Start event was not bracketed'}
    if end is None:
        if censor_at is not None and finite(censor_at) and censor_at >= start['upper']:
            return {**result, 'status': 'right_censored',
                    'lower_seconds': censor_at-start['upper'],
                    'reason': 'Observation ended before the endpoint was observed'}
        return {**result, 'reason': 'Endpoint not observed; no continuous observation horizon established'}
    if not bounded(end) or end['clock_id'] != start['clock_id']:
        return {**result, 'reason': 'Unbounded interval or different monotonic clocks'}
    if end['upper'] < start['lower']:
        return {**result, 'reason': 'Endpoint precedes anchor; recovery cannot be inferred'}
    lower = max(0.0, end['lower']-start['upper'])
    upper = end['upper']-start['lower']
    return {**result, 'status': 'exact' if lower == upper else 'interval',
            'lower_seconds': lower, 'upper_seconds': upper}


def sustained_recovery(samples, *, baseline_rate, after, window_seconds=10.0,
                       sustained_seconds=30.0, fraction=0.9, max_gap=3.0):
    """Nonoverlapping windows of a monotone *stage-specific* cumulative count.

    A window passes only if its conservative rate bound is at least the target.
    Unknown/reset counters or excessive gaps break the sustained sequence. The
    returned event brackets the *start* of a successful sequence and records
    when the full sustained window was confirmed. A short tail is censored.
    """
    if not finite(baseline_rate) or baseline_rate <= 0:
        return {'status': 'unobservable', 'reason': 'Positive comparable stage baseline unavailable', 'event': None, 'windows': []}
    if (not all(finite(v) for v in (after, window_seconds, sustained_seconds, fraction, max_gap))
            or window_seconds <= 0 or sustained_seconds <= 0
            or not 0 < fraction <= 1 or max_gap <= 0):
        raise ValueError('Invalid throughput recovery rule')
    windows, streak = [], []
    first = previous = None
    interrupted = False
    for sample in samples:
        if bounded(sample) and sample['upper'] < after:
            continue
        if (not finite(sample.get('value')) or sample['value'] < 0
                or not bounded(sample) or sample['lower'] < after):
            first = previous = None
            streak = []
            interrupted = True
            continue
        if previous is not None and (sample['lower'] < previous['upper']
                or sample['clock_id'] != previous['clock_id']
                or sample.get('epoch') != previous.get('epoch')
                or sample['upper']-previous['lower'] > max_gap
                or sample['value'] < previous['value']):
            first = None
            streak = []
            interrupted = True
        if first is None:
            first = sample
        previous = sample
        if sample['lower']-first['upper'] < window_seconds:
            continue
        duration_upper = sample['upper']-first['lower']
        rate_lower = (sample['value']-first['value'])/duration_upper
        window = {'lower': first['lower'], 'upper': sample['upper'],
                  'rate_lower': rate_lower, 'qualifies': rate_lower >= fraction*baseline_rate}
        windows.append(window)
        if window['qualifies']:
            streak.append((first, sample))
        else:
            streak = []
        first = sample
        if streak and sample['lower']-streak[0][0]['upper'] >= sustained_seconds:
            beginning = streak[0][0]
            return {'status': 'observed', 'windows': windows,
                    'event': {'name': 'throughput_recovered', 'lower': beginning['lower'],
                              'upper': beginning['upper'], 'clock_id': beginning['clock_id'],
                              'wall_utc': beginning.get('wall_utc'),
                              'source': 'consecutive counter windows',
                              'confirmed_at': sample['upper'], 'fraction': fraction,
                              'baseline_rate': baseline_rate, 'sustained_seconds': sustained_seconds}}
    return {'status': 'right_censored' if windows and not interrupted else 'unobservable', 'event': None,
            'reason': 'No complete qualifying sustained window observed', 'windows': windows}


class RecoveryTimeline:
    VERSION = 'layered-recovery-v1'

    def __init__(self, *, monotonic=time.monotonic, wall=None, clock_id=None):
        self.clock = monotonic
        self.wall = wall or (lambda: datetime.now(timezone.utc).isoformat())
        self.clock_id = clock_id or PROCESS_CLOCK_ID
        self.events = []
        self.observations = []
        self._previous = {}
        self._last_observation = {}
        self._down = set()
        self._lock = threading.RLock()

    def mark(self, name, *, lower=None, upper=None, source='coordinator', **details):
        with self._lock:
            if lower is None and upper is None:
                lower = upper = self.clock()
            if not finite(upper) or (lower is not None and (not finite(lower) or lower > upper)):
                raise ValueError('Invalid event interval')
            event = {'name': name, 'lower': lower, 'upper': upper, 'wall_utc': self.wall(),
                     'clock_id': self.clock_id, 'source': source, 'details': details}
            self.events.append(event)
            return event

    def ingest(self, event):
        """Import an event only from this monotonic clock domain."""
        if not bounded(event) or event['clock_id'] != self.clock_id:
            raise ValueError('Event has invalid bounds or a different monotonic clock')
        with self._lock:
            self.events.append(deepcopy(event))

    def state(self, signal, value, *, lower, upper, source, **details):
        """Observe infrastructure/service state, retaining unavailable probes."""
        if signal not in ('infrastructure', 'service') or value not in (True, False, None):
            raise ValueError('Unsupported state observation')
        if value is not None and type(value) is not bool:
            raise ValueError('State must be boolean or unknown')
        if not finite(lower) or not finite(upper) or lower > upper:
            raise ValueError('Invalid observation interval')
        with self._lock:
            observation = {'signal': signal, 'value': value, 'lower': lower, 'upper': upper,
                           'wall_utc': self.wall(), 'clock_id': self.clock_id, 'source': source,
                           'details': details}
            previous = self._previous.get(signal)
            last = self._last_observation.get(signal)
            if last and lower < last['upper']:
                raise ValueError('Overlapping or out-of-order state observations')
            self.observations.append(observation)
            self._last_observation[signal] = observation
            if value is None:
                return
            if value is False and (previous is None or previous['value'] is True):
                self._down.add(signal)
                self.mark(signal+'_disrupted' if signal == 'infrastructure' else 'service_lost',
                          lower=previous['lower'] if previous else None, upper=upper, source=source)
            elif value is True and signal in self._down and previous and previous['value'] is False:
                self.mark(signal+'_restored', lower=previous['lower'], upper=upper, source=source)
                self._down.discard(signal)
            self._previous[signal] = observation

    def summary(self, *, censor_at=None, observed_endpoints=()):
        with self._lock:
            first = {}
            for event in self.events:
                first.setdefault(event['name'], event)
            # Do not recycle an unrelated recovery that occurred before dispatch.
            dispatch = first.get('fault_dispatch')
            for loss, restore in (('infrastructure_disrupted', 'infrastructure_restored'),
                                  ('service_lost', 'service_restored')):
                first.pop(loss, None)
                first.pop(restore, None)
                if dispatch is None:
                    continue
                for event in self.events:
                    if event['upper'] < dispatch['lower']:
                        continue
                    if event['name'] == loss and loss not in first:
                        first[loss] = event
                    elif event['name'] == restore and loss in first:
                        first[restore] = event
                        break
            metrics = {name: elapsed_interval(first.get(start), first.get(end),
                        censor_at=censor_at if end in observed_endpoints else None)
                       for name, (start, end) in METRICS.items()}
            return {'version': self.VERSION, 'clock_id': self.clock_id,
                    'clock': 'coordinator monotonic seconds; wall UTC for correlation only',
                    'events': deepcopy(self.events), 'observations': deepcopy(self.observations),
                    'metrics': deepcopy(metrics)}
