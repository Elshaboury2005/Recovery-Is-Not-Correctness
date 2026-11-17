# ChaosFlow Transformation Demonstration Runbook

This runbook describes the supported live demonstration path and the evidence it must produce. It uses the existing core Spark/Kafka/HDFS deployment and never treats optional Flink or Hive configuration rendering as runtime evidence.

## Preconditions

```bash
docker compose ps
curl -fsS http://localhost:8000/health
docker exec platform-backend alembic current
```

Expected: core services are running, health is `ok`, and migration `0012_add_hive_query_history` is the head.

## Supported Spark workflow

The authenticated API sequence is:

1. `POST /api/datasets/profiles` for `/app/sample-data/sales_sample.csv` and poll `GET /api/datasets/profiles/{profile_id}` until `succeeded`.
2. `POST /api/workloads/classify` with the persisted profile ID and the CSV pipeline YAML.
3. `POST /api/benchmarks`, then `POST /api/benchmarks/{campaign_id}/execute`; poll the campaign detail until its top-level `status` is terminal.
4. `POST /api/recommendations` using the workload and benchmark IDs.
5. `POST /api/reconfigurations`, then preflight, approve, execute, and poll the operation until `succeeded`.
6. `POST /api/reconfigurations/{operation_id}/rollback`; verify `rolled_back`, retained evidence, and `production_mutation_applied=false`.
7. Recheck `/health` and platform readiness.

The latest live evidence from 2026-11-06 is:

| Artifact | ID | Result |
|---|---|---|
| Dataset profile | `506db844-8d37-44a0-a5a2-7b4c194a67b3` | Existing exact CSV profile reused |
| Workload | `69add197-e9f0-43b2-8eb4-982486065cbd` | Spark-compatible classification |
| Benchmark campaign | `4b940b8b-4d69-4724-b4d6-ff84a4732142` | `succeeded`; one measured Spark run, 48.04 seconds, 0.312 records/sec |
| Recommendation | `2cf36e50-88a6-4c92-b60c-600fb24fb7e6` | Spark selected from correctness-passed measured evidence |
| Reconfiguration | `4d5aea95-b4db-4082-af04-3d05b2d8236a` | Isolated execution `succeeded`, 20 input/15 output, validator `PASS`, then `rolled_back` |

The isolated reconfiguration output is under `hdfs://namenode:9000/data/chaosflow-reconfigurations/4d5aea95-b4db-4082-af04-3d05b2d8236a`. No production routing mutation was applied.

## Frontend verification

When the cached Node-capable evaluation image is available:

```bash
docker run --rm \
  -v "$PWD/frontend:/input:ro" \
  chaosflow-frontend-eval:latest \
  sh -lc 'rm -rf /tmp/chaosflow-frontend && cp -a /input /tmp/chaosflow-frontend && rm -rf /tmp/chaosflow-frontend/node_modules && ln -s /app/node_modules /tmp/chaosflow-frontend/node_modules && cd /tmp/chaosflow-frontend && npm run build && npm run lint && npm test'
```

The latest source-level result is a successful build with 3,599 transformed modules, zero-warning lint, and 28 test files / 264 tests passing.

The browser route smoke spec is `frontend/e2e-dev/transformation-routes.spec.ts`. In this environment, the standard image has no bundled Chromium, so the verified alternative used the real host Chrome CDP endpoint with `frontend/e2e-dev/cdp-route-smoke.mjs` and `frontend/e2e-dev/cdp-viz-smoke.mjs`, authenticated `E2E_USERNAME`/`E2E_PASSWORD`, and the current Vite source. This passed six transformation routes, all 12 visualization presets, animation pause behavior, and reduced-motion fallback. It must not be replaced with a mock result.

## Airflow intelligence orchestration

Verify scheduler parsing without triggering a duplicate live benchmark:

```bash
docker exec platform-airflow-scheduler airflow dags list
docker exec platform-airflow-scheduler airflow dags show transformation_intelligence_dag
docker exec platform-airflow-scheduler airflow dags list-import-errors --output json
```

`transformation_intelligence_dag` expects `source_uri` and `pipeline_yaml` in `dag_run.conf`, then sequences the persisted backend APIs through safe reconfiguration preflight. It does not implicitly execute or mutate production routing. Trigger it only with a controlled demonstration configuration and valid `BACKEND_USERNAME`/`BACKEND_PASSWORD` Airflow environment variables.

## Optional runtime checks

```bash
docker compose --profile flink config
docker compose --profile hive config
docker compose --profile full config
```

These commands verify Compose rendering only. Start Flink/Hive and run their real health/query/benchmark checks only when the required images, Hive client driver, and Flink job artifact are available.
