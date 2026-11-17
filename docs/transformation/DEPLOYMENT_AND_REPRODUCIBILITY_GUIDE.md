# ChaosFlow Deployment and Reproducibility Guide

## Prerequisites

- Docker Engine and Docker Compose.
- At least the core Spark/Kafka/HDFS/PostgreSQL resources described in `docker-compose.yml`.
- Registry access for optional Flink/Hive images and for rebuilding the frontend image.
- A browser-capable Playwright environment for authenticated route smoke tests. If the Node evaluation image has no bundled browser, use the host-Chrome CDP runner described in `DEMONSTRATION_RUNBOOK.md`.

## Environment

Copy `.env.example` to `.env` and set credentials/secrets appropriate for the environment. Do not commit `.env` or log credentials.

## Core startup and migrations

```bash
docker compose up -d
docker exec platform-backend alembic upgrade head
docker compose ps
curl -fsS http://localhost:8000/health
docker exec platform-airflow-scheduler airflow dags list
docker exec platform-airflow-scheduler airflow dags show transformation_intelligence_dag
```

The core path must remain usable without optional services.

## Optional profiles

Validate configuration before attempting startup:

```bash
docker compose --profile flink config
docker compose --profile hive config
docker compose --profile full config
```

When registry access and compatible images are available:

```bash
docker compose --profile flink up -d flink-jobmanager flink-taskmanager
docker compose --profile hive up -d hive-metastore hive-server
```

Profile rendering is not runtime proof. Confirm engine/Hive health APIs and execute a real supported workload before changing status.

## Verification

```bash
docker exec platform-backend pytest -q -m 'not integration'
docker exec platform-backend pytest -q tests/infrastructure tests/hive tests/reconfiguration tests/benchmark tests/workload tests/engines
docker exec platform-backend alembic current
curl -fsS http://localhost:8000/health
```

Frontend source verification uses the cached Node-capable image when host Node/npm are unavailable; the exact command is in `DEMONSTRATION_RUNBOOK.md`.

## Demonstrations

Use `DEMONSTRATION_RUNBOOK.md` for the authenticated profile → classification → benchmark → recommendation → reconfiguration → rollback workflow, topology comparison, frontend checks, Airflow DAG parsing, and optional-runtime evidence rules.

## Service access

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/health`
- Backend OpenAPI: `http://localhost:8000/docs`
- Airflow: `http://localhost:8081`
- Prometheus/Grafana: see the published ports in `docker-compose.yml`.

## Troubleshooting and safety

- If an optional image cannot be pulled, record the registry error; do not substitute a mock or claim runtime success.
- Do not run `docker compose down -v` on a deployment containing preserved research data.
- Do not reset the dirty worktree.
- Keep new benchmark outputs in transformation-specific database records and isolated HDFS namespaces.
- Treat a recommendation as evidence, not permission for production mutation.
