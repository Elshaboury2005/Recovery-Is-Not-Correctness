# Installation

ChaosFlow is a Docker Compose development and research platform. The supported
local deployment is a single host running the pinned services in
`docker-compose.yml`.

## Prerequisites

- Docker Engine with Docker Compose v2.
- At least 8 CPU threads and 16 GiB RAM are recommended for the complete stack.
- At least 25 GiB free disk for images, named volumes, sample data, and logs.
- Git, `curl`, and a POSIX shell for the Linux/macOS commands below.
- PowerShell 7 or later for `scripts/setup-env.ps1` on Windows.

The research campaigns were run on a single host. A local deployment is not an
independent-host reproduction and must not be described as one.

## Configure secrets

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Set unique values for `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`,
`GRAFANA_ADMIN_PASSWORD`, `ADMIN_PASSWORD`, `AIRFLOW_DB_PASSWORD`,
`AIRFLOW_FERNET_KEY`, and `AIRFLOW_ADMIN_PASSWORD` before using a shared
environment. The committed `.env.example` contains placeholders only. Never
commit `.env`.

If an existing Airflow metadata volume is being reused, supply its currently
active Fernet key before restarting Airflow. Do not generate a replacement key
until an approved re-encryption and rollback procedure is available.

On Windows, the setup helper can generate a local `.env`:

```powershell
.\scripts\setup-env.ps1
```

## Start the platform

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

The main endpoints are:

- Frontend: <http://localhost:3000>
- FastAPI/OpenAPI: <http://localhost:8000/docs>
- Spark UI: <http://localhost:8080>
- HDFS NameNode UI: <http://localhost:9870>
- Airflow: <http://localhost:8081>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3001>

The stack owns named Docker volumes for PostgreSQL, Kafka, Spark, HDFS,
Airflow, Grafana, and optional Hive/Flink components. Do not run
`docker compose down -v` in a research workspace unless all persistent data
has been archived and deletion has been explicitly approved.

## Stop the platform

```bash
docker compose stop
```

`stop` preserves volumes. Use `docker compose down` only when the container
definitions themselves should be removed; it still does not authorize volume
deletion.

## Local tests

```bash
docker exec platform-backend pytest -q -m 'not integration'
cd frontend
npm ci
npm run lint
npm test -- --run
npm run build
```

Integration and Playwright tests require the running services and should be
executed only against an isolated, disposable evaluation environment.
