# T4 Root-Cause Analysis

## Finding

The missing T4 values are a mixture of a measurement defect and a real
finite-workload censoring problem. They are not evidence that Kafka recovery
failed.

## Defect in the original probe

In the primary runner's `throughput_endpoint`, the continuity reset condition
was effectively:

```text
current.upper - previous.lower > 3 seconds
```

For interval-valued samples, this spans the previous interval, the gap, and
the current interval. With approximately 0.5-second polling and HTTP
intervals around 1.4 seconds, the expression can exceed three seconds even
when the gap between adjacent observations is within the permitted three
seconds. The clean T4 sequence is then reset repeatedly.

The independent repair uses the actual inter-sample gap:

```text
current.lower - previous.upper > 3 seconds
```

It preserves the baseline threshold, the 10-second window requirement, the
30-second sustained requirement, the T2 origin, and all raw lower/upper
bounds. No endpoint is created when the required samples are absent.

## Classification impact

| Classification | Original | Corrected |
|---|---:|---:|
| Observed | 115 | 175 |
| Right-censored | 95 | 35 |
| Unobservable | 30 | 30 |

All 60 C1/C2 runs change from recorded right-censoring to corrected observed
T4. Corrected C1 and C2 are 15/15 observed in both observer states. This is
the key reason that a Kafka-specific follow-up is not necessary for the T4
question.

## Remaining censoring

The remaining 35 corrected right-censored records are concentrated in:

- C7 checkpoint recovery: 11 ON and 10 OFF;
- C3 Spark-worker failure: 5 ON and 7 OFF;
- C4 DataNode failure: 1 ON and 1 OFF.

C7 is the relevant unresolved endpoint gap. The fixed 1,000,000-row workload
frequently reaches its terminal state after only about 25–30 seconds of
post-T2 processing, before the 30-second T4 confirmation can be completed.
Repeating the same finite workload would reproduce the censoring mechanism.

## Follow-up implication

If a follow-up is run, it must be a separate protocol using a longer finite
workload or a separately justified endpoint. The first step is a pilot that
verifies enough post-T2 activity, fault activation/restoration, observer
evidence, and correctness. A valid pilot does not automatically become a
main observation.
