# API documentation

FastAPI serves the interactive contract at `/docs` and the machine-readable
OpenAPI document at `/openapi.json` when the backend is running.

## Endpoint groups

| Prefix | Purpose |
|---|---|
| `/api/auth` | Login and access-token handling. |
| `/api/pipelines` | Pipeline definitions, templates, and validation. |
| `/api/pipeline-runs` | Start, inspect, cancel, stream progress, and inspect outputs. |
| `/api/experiments` | Reliability experiment definitions and reports. |
| `/api/messaging` | Kafka status and producer/consumer signals. |
| `/api/storage` | HDFS/output metadata, previews, and bounded downloads. |
| `/api/metrics` | Prometheus-facing application metrics. |
| `/api/health` | Liveness and system dependency status. |
| `/api/benchmarks`, `/api/workloads`, `/api/datasets` | Dataset and benchmark metadata. |
| `/api/recommendations`, `/api/reconfigurations` | Explicitly bounded planning/reconfiguration workflows. |
| `/api/hive`, `/api/infrastructure`, `/api/engines` | Read-only analytical, topology, and engine capability boundaries. |

Most application endpoints require a bearer token from `/api/auth/login`.
The backend rejects placeholder production credentials and enforces bounded
output preview/download tokens.

## Progress and evidence semantics

Server-sent events expose progress and terminal states for UI use. Consumers
must preserve `null`, `UNKNOWN`, `INCOMPLETE`, and `NOT_OBSERVABLE`; these values
are not zeroes. Research analyses should use the retained evidence files and
independent oracle rather than scraping UI text.

## Client examples

```bash
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/openapi.json -o /tmp/chaosflow-openapi.json
```

The exact request and response schemas are generated from the running revision;
do not publish a copied OpenAPI document as if it were version-independent.
