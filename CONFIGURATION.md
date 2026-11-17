# Configuration

Runtime configuration is loaded from `.env` and passed to the Compose services.
Start from `.env.example`; do not copy credentials from historical logs or
research archives.

| Area | Variables | Notes |
|---|---|---|
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT` | Database and host port. |
| Backend | `APP_ENV`, `LOG_LEVEL`, `BACKEND_PORT`, `DATABASE_URL` | Use the `postgres` service name inside Compose. |
| Authentication | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Replace all placeholders before deployment. |
| CORS | `CORS_ORIGINS` | Use exact frontend origins in shared environments. |
| Kafka | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_CLIENT_ID`, `KAFKA_DEFAULT_PARTITIONS`, `KAFKA_PRODUCER_ACKS` | `kafka:9092` is the internal endpoint. |
| Spark | `SPARK_MASTER_URL`, `SPARK_JOBS_PATH`, `SPARK_SUBMIT_TIMEOUT_SECONDS` | The Compose mount is read-only for Spark jobs. |
| HDFS | `HDFS_NAMENODE_URL`, `HDFS_USER`, `HDFS_DEFAULT_REPLICATION` | Single-node local defaults are not durability evidence. |
| Airflow | `AIRFLOW_UID`, `AIRFLOW_DB_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_ADMIN_USERNAME`, `AIRFLOW_ADMIN_PASSWORD`, `AIRFLOW_ADMIN_EMAIL` | Required before Compose renders Airflow. Keep the current Fernet key stable for an existing metadata database; rotate only through an approved migration. |
| ChaosLab | `PROJECT_CONTAINER_PREFIX` | Safety checks must point only to this Compose project. |
| Output limits | `OUTPUT_PREVIEW_MAX_ROWS`, `OUTPUT_PREVIEW_MAX_FILE_BYTES`, `OUTPUT_DOWNLOAD_MAX_BYTES`, `OUTPUT_DOWNLOAD_TOKEN_TTL_SECONDS` | Bound browser preview and download work. |

## Configuration validation

```bash
docker compose config --quiet
docker exec platform-backend python -m pytest -q tests/test_config.py tests/test_config_validator.py
```

Changing service names, Compose project names, ports, or volume names can make
existing experiment evidence incomparable. Record such changes in a new
protocol version; do not edit historical protocol files in place.

The Airflow values are intentionally absent from the committed `.env.example`
as active credentials. Copy the template, provide operator-controlled values,
and keep `.env` private. The Compose configuration fails closed when the
Airflow database password, Fernet key, or admin password is missing. The
existing running Airflow containers were not restarted during this audit.
