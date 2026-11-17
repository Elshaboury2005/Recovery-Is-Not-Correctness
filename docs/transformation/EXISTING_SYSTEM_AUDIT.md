# Existing System Audit

Audit date: 2026-11-06

## Executive summary

ChaosFlow is an existing configuration-driven Spark pipeline and reliability platform, not an empty scaffold. The baseline has real local/container execution, Kafka messaging, Spark submission, HDFS output, Airflow scheduling, PostgreSQL persistence, Prometheus/Grafana observability, JWT authentication, an accessible React frontend, and a ChaosLab fault/recovery workflow.

The transformation gap is additive and substantial: Flink, Hive, dataset intelligence, architecture benchmarking/recommendation, safe reconfiguration, complete topology visualization, and end-to-end workflows are absent from the baseline. The implementation must preserve the existing Spark and research paths.

## Current architecture

```text
React/Vite frontend (Nginx, :3000)
          |
          v
FastAPI backend (:8000) -- PostgreSQL 16
      |       |       |\
      |       |       | \-- Prometheus (:9090) -> Grafana (:3001)
      |       |       \---- HDFS NameNode (:9000/:9870) -> DataNodes
      |       \------------ Kafka KRaft (:9093)
      \------------------- Spark master (:7077/:8080) -> Spark worker(s)

Airflow webserver (:8081) and scheduler use a separate Airflow PostgreSQL database.
```

The Compose file defines the core services and mounts application source into the backend for development. It currently has no `profiles:` sections.

## Existing services and versions

| Service | Baseline configuration | Status observed |
|---|---|---|
| FastAPI backend | Python 3.11 image, app version 0.1.0 | Running; liveness/readiness passed |
| PostgreSQL | `postgres:16-alpine` | Connected |
| Kafka | `confluentinc/cp-kafka:7.6.0`, single KRaft broker | Connected; 1 broker observed |
| Spark | `bitnamilegacy/spark:3.5.0`, standalone master/worker | Connected; 2 workers observed in readiness response |
| HDFS NameNode | `bde2020/hadoop-namenode:2.0.0-hadoop3.2.1-java8` | Connected |
| HDFS DataNode | `bde2020/hadoop-datanode:2.0.0-hadoop3.2.1-java8` | 2 live DataNodes observed in readiness response |
| Airflow | `2.10.3` built image, separate metadata PostgreSQL | Running in current stack |
| Prometheus | `prom/prometheus:v2.54.0` | Running in current stack |
| Grafana | `grafana/grafana:11.2.2` | Running in current stack |
| Frontend | Node 20 build, Nginx runtime | Existing built image running |

## Backend modules

- `app/pipeline`: strict Pydantic pipeline schema, parser, validator, generator, executor, progress, streaming progress, and throughput.
- `app/plugins`: CSV, JSON, Kafka, and API sources; local/HDFS storage; transformation processors.
- `app/spark`: Spark submission and progress integration.
- `app/messaging`: Kafka admin, producer, consumer, and configuration.
- `app/storage`: HDFS client/configuration and Spark output manifest logic.
- `app/reliability`: safety validation, Docker controller, fault injectors, experiment runner/models, recovery observer/timeline, metrics, reports, and correctness validators.
- `app/api/routes`: health, auth, pipelines, pipeline runs/templates, storage, Spark, messaging, experiments/reports, dashboard, metrics, and reliability analysis.
- `app/models`: users, pipelines/versions/runs/events, metrics, faults, experiments/events/runs, reports, and audit logs.

## API inventory from the running application

### Health and observability

- `GET /health`
- `GET /api/health`
- `GET /api/system/status`
- `GET /api/spark/health`
- `GET /api/storage/health`
- `GET /api/messaging/health`
- `GET /api/metrics`
- `GET /api/metrics/{pipeline_id}`
- `GET /metrics`

### Authentication and dashboard

- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/refresh`
- `GET /api/dashboard/summary`

### Pipelines and runs

- `POST /api/pipelines/validate`
- `POST /api/pipelines/run`
- `GET /api/pipeline-templates`
- `GET /api/pipeline-runs`
- `GET /api/pipeline-runs/{run_id}`
- `GET /api/pipeline-runs/{run_id}/progress`
- `GET /api/pipeline-runs/{run_id}/events`
- `GET /api/pipeline-runs/{run_id}/stream`
- `POST /api/pipeline-runs/{run_id}/cancel`
- `GET/POST /api/pipeline-runs/{run_id}/output*`

### Messaging, experiments, and reports

- `GET/POST /api/messaging/topics*`
- `GET/POST /api/experiments`
- `GET /api/experiments/allowed-targets`
- `GET /api/experiments/options`
- `GET /api/experiments/{experiment_id}`
- `GET /api/experiments/{experiment_id}/events`
- `POST /api/experiments/{experiment_id}/run`
- `POST /api/experiments/{experiment_id}/cancel`
- `GET /api/reports`
- `GET /api/reports/{report_id}`
- `POST /api/ai/reliability-analysis`

## Frontend route inventory

- `/login`
- `/`
- `/pipelines`
- `/pipelines/:runId`
- `/reliability`
- `/reports`
- `/reports/:id`
- `/dev/viz` in development builds only

The sidebar currently exposes Dashboard, Pipelines, Reliability Testing, and Reports. New Dataset Intelligence, Architecture Advisor, Benchmark Lab, Reconfiguration Center, Hive SQL Explorer, and infrastructure topology routes are not present.

## Pipeline execution flow

1. A YAML request is parsed into strict Pydantic models.
2. Business validation checks schema, streaming, operation, source, and storage constraints.
3. A generator builds a typed execution plan with source, processor, and storage steps.
4. The executor runs local/pandas-compatible paths or submits Spark work through `SparkJobSubmitter`.
5. Kafka may be used for messaging and streaming progress is tracked via SSE/event state.
6. Spark/HDFS output is persisted and independently inspected through manifest/output-oracle logic.
7. FastAPI persists pipeline/run/events/metrics and the frontend observes progress.

The current configuration supports explicit Spark processing, but no engine-selection abstraction or Flink branch.

## Database schema overview

Current ORM entities include:

- `users`
- `pipelines`
- `pipeline_versions`
- `pipeline_runs`
- `pipeline_run_events`
- `metrics`
- `fault_injections`
- `experiments`
- `experiment_runs`
- `experiment_events`
- `reports`
- `audit_logs`

Alembic migrations run from `0001_initial_schema.py` through `0006_add_experiment_events.py`. New transformation data should use forward-only migrations and preserve all existing tables and records.

## Monitoring and visualization flow

The backend exposes polling and server-sent-event run progress. The frontend maps run progress into a four-stage Source → Kafka → Spark → HDFS visualization. The Three.js view has a 2D fallback, context-loss handling, quality controls, and cleanup tests. It does not yet consume a service-topology event stream or represent Flink/Hive/individual infrastructure nodes.

## Current tests and evidence

- Backend non-integration suite: **681 passed, 19 skipped, 40 deselected, 1 warning** in the existing backend container.
- Live liveness: pass.
- Live readiness: PostgreSQL, Kafka, Spark, and HDFS connected.
- Frontend tests were not rerun in this shell because host Node/npm are unavailable. The repository contains existing Vitest, Playwright, accessibility, and visualization tests, and the existing frontend container is running a previously built artifact; that is not new verification for this transformation.

## Reusable components

- Existing strict pipeline models and validator.
- Spark job submitter and progress parsing.
- Kafka admin/producer/consumer modules.
- HDFS client and committed-output manifest/oracles.
- Existing SSE/event infrastructure.
- Reliability safety boundary, Docker controller, fault injectors, recovery timeline, and correctness validators.
- Existing auth, request dependency patterns, SQLAlchemy/Alembic setup, design system components, and visualization fallback.

## Limitations and target gaps

1. No Flink service, adapter, job submission, checkpoint integration, metrics, or correctness path.
2. No Hive service/metastore/query execution or SQL Explorer.
3. No dataset profiling service, persistence, async jobs, or UI.
4. No explainable workload classifier or engine capability registry.
5. No fair Spark/Flink benchmark campaign model or orchestration.
6. No evidence-backed architecture recommendation engine.
7. No safe reconfiguration state machine, dry run, approval, or rollback workflow.
8. No Flink-aware ChaosLab experiments.
9. No deployed infrastructure topology API or complete 3D explorer.
10. Compose has no optional profiles and core startup assumes Spark/HDFS/Kafka dependencies.

## Compatibility and preservation requirements

- Existing YAML configurations remain valid unless a versioned, documented extension is required.
- Core Spark operation remains possible without optional Flink/Hive services.
- New runs, benchmarks, and evidence use separate namespaces and provenance.
- No historical research outputs, frozen protocols, run logs, or manuscript artifacts are modified.
- No destructive volume cleanup is part of setup or testing.

## Recommended implementation sequence

1. Add optional deployment boundaries and service availability contracts.
2. Create unified engine contracts and preserve Spark behind them.
3. Add Flink capability validation and real execution path.
4. Implement profiling and persistence.
5. Add workload classification and capability matching.
6. Build benchmark orchestration and result storage.
7. Add recommendation and safe reconfiguration workflows.
8. Add Hive discovery/query integration.
9. Extend ChaosLab and topology events.
10. Build integrated frontend workflows and infrastructure 3D explorer.
11. Execute full integration/regression validation and publish reproducible evidence.
