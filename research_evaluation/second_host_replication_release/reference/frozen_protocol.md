# ChaosFlow observer overhead and recovery diversity protocol

Protocol ID: `CHAOSFLOW-240-OBSERVER-RECOVERY-V1`  
Campaign: `chaosflow_240_campaign_20261120_1`  
Status: **blocked before final freeze; C5 pilot correctness gate failed**

## Primary design

The main design is 8 scenarios × 2 observer states × 15 repetitions = 240
qualifying observations. Fifteen randomized blocks each contain one
observation of every scenario/observer cell. The block order is generated with
Python `random.Random(20261120)` and is recorded in `run_schedule.csv`.
Runs are strictly sequential.

The workload, schema, transformation, Kafka topic, HDFS output path, and
checkpoint path are unique per run. The immutable dataset is the repository's
1,000,000-row `sales_large.csv` fixture. The expected output is the exact
typed full-row multiset after dropping null rows and retaining `amount > 0`
rows: 966,002 occurrences.

## Observer states

- `OBSERVER_ON`: launch the repository `RecoveryObserver` in the campaign
  backend container. It polls infrastructure, functional service, and
  application-progress probes at 0.5 s and records its own evidence.
- `OBSERVER_OFF`: do not launch that experimental observer. The repository's
  independent minimal collector remains active, with identical polling and
  output-validation behavior, so OFF does not remove the measurement system.

The minimal collector is the prespecified measurement system for the primary
recovery endpoints in both states. It uses one monotonic clock per attempt and
retains bracket intervals rather than fabricating point timestamps.

## Scenario definitions

| ID | Frozen meaning | Activation and restoration evidence |
|---|---|---|
| C0 | No fault control | No fault action; baseline and completion timings only. T0–T4 are `not_applicable`. |
| C1 | Kafka container stop | Safety-gated `container_stop` on the campaign Kafka container for 5 s; Docker state/event evidence and broker functional probe. |
| C2 | Kafka container restart | Safety-gated `container_restart` on the campaign Kafka container; Docker restart event, new start boundary, and broker functional probe. |
| C3 | Spark worker failure | Safety-gated `container_stop` on the campaign Spark worker for 5 s; Spark master worker membership and container state evidence. |
| C4 | HDFS DataNode failure | Safety-gated `container_stop` on the campaign DataNode for 5 s; DataNode state, WebHDFS/DataNode readiness, and HDFS report evidence. |
| C5 | Network fault | Safety-gated 100% `tc netem` packet loss on the campaign DataNode `eth0` only, for 5 s; `tc qdisc` activation/removal and HDFS functional probe. The campaign DataNode has only the Compose-scoped `NET_ADMIN` capability required by this fault. No host/shared interface is changed. |
| C6 | Storage fault | Write at most 256 MiB to a run-specific scratch file under the fresh campaign DataNode storage bind mount for 5 s, then remove it. The target is campaign-owned storage pressure, not a host filesystem or historical volume. |
| C7 | Checkpoint-related recovery | After the run-scoped streaming checkpoint metadata exists, atomically rename one run-scoped metadata file to a quarantine name for 1 s and restore it. This is a real checkpoint-path availability exposure, not a configuration-only change. |

If a pilot shows that a scenario cannot meet its activation, restoration, or
correctness gates safely, the scenario is marked unsupported and the main
campaign stops before protocol freeze. C5 is currently blocked: activation and
rollback are reproducible, but two post-repair attempts ended with UNKNOWN
independent correctness validation after the same HDFS metadata read failure.
No unapproved substitute is silently inserted; changing C5 requires explicit
approval and a documented amendment.

## Recovery endpoints

For C1–C7, the collector records the following independently. Every event is
stored as a lower/upper interval on the same monotonic clock; intervals are
never subtracted across clocks.

- T0: first independently observed activation of the intended fault.
- T1: affected container/process returns to the specified running state.
- T2: affected service passes its functional readiness probe.
- T3: application progress counter resumes increasing after T2.
- T4: throughput reaches at least 90% of a frozen matched baseline for three
  consecutive valid 10-second windows.
- T5: independent typed full-row correctness validation completes.

Derived intervals are reported only when both endpoint intervals are valid:
T1−T0, T2−T0, T3−T0, T4−T0, T2−T1, T3−T2, and T4−T3. Missing endpoints,
right-censored endpoints, and unobservable endpoints remain explicit.

For C0, recovery milestones are not fabricated. End-to-end execution,
throughput, resource use, and T5 correctness are reported as control metrics.

## Qualification and retry rules

An attempt qualifies only when its slot assignment, dataset/configuration,
required instrumentation, fault activation/restoration evidence (where
applicable), terminal observations, cleanup, and both independent correctness
checks are complete and positive. An exposed attempt with incorrect or
unproven output is retained as an invalid/non-qualifying scientific outcome;
it is never silently replaced or counted as a qualifying observation.

Infrastructure or instrumentation failures are `INVALID`, remain immutable in
`invalid_attempts/`, and receive a new attempt ID if a replacement is needed.
The original is never rewritten. Automatic replacement is bounded to two
attempts per slot; a repeated systematic failure pauses the runner.

## Resource and cleanup policy

One measured attempt is active at a time. Before the next attempt, the runner
checks memory, disk, project health, and restoration state. Per-run Kafka
topics, HDFS output paths, checkpoints, and storage scratch files are deleted
only after exact oracle evidence and checksums are durably recorded; cleanup is limited to the current
campaign's run-scoped resources. No historical volume or dataset is touched.

## Prespecified analysis

Primary comparisons are observer ON versus OFF within scenario and block,
with scenario-by-observer interaction as the secondary model. The analysis
reports descriptive statistics, paired effects, confidence intervals,
multiple-comparison correction, block/order checks, missing/censored endpoints,
invalid-attempt accounting, and sensitivity analyses. The old 90-run campaign
and the earlier 72-run pilot remain separate cohorts.


## Pilot repair continuation and final freeze (2026-11-20T04:57:19.780799+00:00)

All 16 pilot cells are strict-valid after the campaign-scoped HDFS transport, Spark readiness, checkpoint lookup, and observer launch repairs. The approved matrix and qualification criteria are unchanged. The frozen C0 baseline is 11015.732 input records/s, computed from both valid C0 controls using independent cumulative `records_in` slopes.

Status: **FROZEN BEFORE MAIN CAMPAIGN**.
