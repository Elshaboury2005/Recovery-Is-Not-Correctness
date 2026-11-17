# Troubleshooting

## Services do not become healthy

```bash
docker compose ps
docker compose logs --tail=100 backend postgres kafka spark-master namenode
```

Check available memory and disk before rebuilding. Spark, Kafka, and HDFS are
resource-sensitive on a 16 GiB host.

## Authentication fails

Confirm that `.env` contains non-placeholder `ADMIN_USERNAME`, `ADMIN_PASSWORD`,
and `JWT_SECRET_KEY`. Existing database state can retain earlier credentials;
do not remove the PostgreSQL volume to reset it in a research workspace.

## Kafka or Spark progress is missing

Check the internal service endpoints (`kafka:9092`, `spark://spark-master:7077`)
from inside containers. A running container is not proof of application
progress; inspect the run's retained progress evidence.

## HDFS output is unavailable

Check NameNode/DataNode health and the configured HDFS path. A successful HDFS
probe does not establish physical durability. Preserve `UNKNOWN` or
`NOT_OBSERVABLE` when an endpoint cannot be measured.

## Tests cannot run

The backend test suite is containerized. Frontend lint/build/test requires Node
and npm; install from the lockfile in a disposable development environment.
Do not substitute a browser screenshot or a stale historical report for a
current test result.
