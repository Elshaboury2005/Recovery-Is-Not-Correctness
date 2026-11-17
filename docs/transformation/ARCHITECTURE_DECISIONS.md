# Architecture Decisions

## ADR-0001 — Preserve the existing core deployment

Status: accepted

The current Spark/Kafka/HDFS/PostgreSQL/Airflow/observability deployment remains the default core path. Optional Flink and Hive capabilities must not be required for basic existing Spark pipeline operation.

Reason: the master prompt requires backward compatibility and preservation of existing research workflows.

## ADR-0002 — Treat Flink and Hive as capability-scoped optional services

Status: proposed for Phase 1

Flink and Hive will be enabled through explicit Compose profiles or additive overrides. The backend will expose availability and capability state rather than reporting an unavailable optional service as healthy.

Reason: the environment is resource-constrained and the core stack is already used by research artifacts.

## ADR-0003 — Use a shared engine contract with explicit capability differences

Status: accepted for Phase 2

Spark and Flink will implement a common orchestration contract, but engine-specific semantics, checkpoint formats, transformations, connectors, and recovery signals will remain explicit. Unsupported operations must fail validation before submission.

## ADR-0004 — Separate new evidence from historical research evidence

Status: accepted

New benchmarks, profiles, and demonstrations will use dedicated transformation evidence paths and database records. Existing research evaluation directories, frozen outputs, run logs, and manuscript-related artifacts are read-only from this task's perspective.

## ADR-0005 — Progress is gate-based and evidence-backed

Status: accepted

The reported overall percentage counts only completed phase gates. A source file, container startup, or mocked test does not make a feature complete.

## ADR-0006 — Separate safe reconfiguration verification from production mutation

Status: accepted

Approved reconfiguration operations execute in an isolated evidence namespace, run an independent correctness validator, retain audit evidence, and expose rollback recording. The current implementation does not silently change production routing.

Reason: a recommendation is evidence for an operator decision, not authorization for an irreversible live cutover.

## ADR-0007 — Keep transformation orchestration thin and API-driven

Status: accepted

The transformation Airflow DAG sequences authenticated backend APIs and polls their durable state. Profiling, classification, benchmark fairness, recommendation ranking, and safety guards remain backend-owned. The DAG stops at safe reconfiguration preflight unless a separately controlled operator action is requested.

Reason: this keeps orchestration observable and reproducible without duplicating business logic or bypassing the platform's security and transition guards.
