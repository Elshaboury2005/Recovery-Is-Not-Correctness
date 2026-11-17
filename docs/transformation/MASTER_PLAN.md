# ChaosFlow Platform Transformation Master Plan

Status: active
Baseline date: 2026-11-06

## Objective

Extend the existing ChaosFlow platform into an integrated, evidence-driven data-engineering control plane while preserving the existing Spark, Kafka, HDFS, Airflow, authentication, monitoring, ChaosLab, frontend, and research artifacts.

The implementation will not label a feature complete until its implementation, integration, error handling, documentation, tests, and a real-input demonstration are available.

## Phase sequence

| Phase | Scope | Completion gate |
|---:|---|---|
| 0 | Audit and baseline | Existing architecture, APIs, routes, deployment, tests, limitations, and preservation constraints documented. |
| 1 | Infrastructure extension | Compose profiles and verified Flink/Hive service boundaries exist without making core Spark operation depend on optional services. |
| 2 | Unified engine layer | Shared engine contracts exist; Spark is preserved behind the contract; Flink capability checks and real execution evidence exist. |
| 3 | Dataset profiling | Profile service, persistence, APIs, progress, validation, tests, and real-data UI exist. |
| 4 | Workload intelligence | Deterministic classification and engine-capability matching are explainable and tested. |
| 5 | Benchmarking engine | Controlled, persisted, correctness-aware benchmark runs and comparisons execute against real workloads. |
| 6 | Architecture selection | Recommendations are evidence-backed, objective-sensitive, explainable, and return insufficient-evidence explicitly. |
| 7 | Safe reconfiguration | Proposal, preflight, approval, dry run, controlled apply, verification, and supported rollback are implemented. |
| 8 | Hive analytics | Verified table discovery, registration, query execution, safe limits, history, and UI are implemented for supported outputs. |
| 9 | ChaosLab multi-engine | Flink-aware fault/recovery observation is added without changing historical Spark evidence. |
| 10 | Infrastructure 3D explorer | Live deployed topology, planned topology comparison, node inspection, filters, events, and WebGL stability are implemented. |
| 11 | Frontend refinement | New workflows are coherent, accessible, responsive, data-backed, and integrated with existing routes. |
| 12 | Integration and regression | Cross-service, end-to-end, frontend, performance, and historical-preservation gates are executed and defects addressed. |
| 13 | Documentation and evaluation | Reproducible deployment, demonstrations, test evidence, benchmark evidence, final report, and final status matrix are complete. |

## Progress calculation

The user-requested progress percentage is reported after each completed phase. Until a more evidence-based weighted measure is available, the transformation percentage uses the 14 planned phases as equal gates:

`overall percentage = completed phase gates / 14 × 100`

This percentage is deliberately conservative. A phase is counted only when its completion gate is met; source files alone do not count.

## Current next step

Phase 0, the supported Phase 10 infrastructure explorer gate, the Phase 11 frontend refinement gate, the Phase 12 integration/regression gate, and the Phase 13 documentation/evaluation gate are complete, yielding **36% (5 of 14)** under the conservative equal-gate measure. Phase 1/2/8/9 remain blocked or partially supported where optional Flink/Hive runtime and artifact evidence are unavailable. The next work is limited to registry-dependent runtime/image retries and a controlled optional Airflow DAG demonstration; no blocked runtime result is to be inferred from profile rendering or Spark-only evidence.
