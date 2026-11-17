# Security

## Local development

Copy `.env.example` to `.env` and replace every credential placeholder. `.env`
is ignored by Git and must remain local. Rotate any credential that has ever
been exposed in a log, shell history, screenshot, archive, or shared notebook.

## Deployment considerations

- The backend mounts `/var/run/docker.sock` so ChaosLab can inspect and control
  approved project containers. Treat this as a privileged development
  capability; do not expose it to an untrusted multi-tenant deployment.
- The Compose file publishes development UIs and data services on host ports
  (PostgreSQL, Kafka, Spark, HDFS, Airflow, Prometheus, Grafana, and the
  application). Bind these to a private network or remove the host mappings
  before deployment; source publication does not secure an exposed service.
- The local Compose stack intentionally uses plaintext Kafka, Spark, HDFS, and
  WebHDFS endpoints for reproducible single-host development. Production needs
  authenticated/encrypted transport, restricted network policy, and separate
  service credentials.
- The backend Compose command runs without auto-reload. Keep file watching and
  development-only debug settings out of production overlays.
- Restrict `CORS_ORIGINS`, database ports, Grafana, Airflow, and Docker API
  access in shared environments.
- Use unique PostgreSQL, JWT, admin, Grafana, and Airflow Fernet secrets.
- Do not infer that a passing health check proves data correctness or durable
  storage.

## Reporting

Do not place live secret values in an issue or commit. Provide a sanitized
description, affected revision/path, exposure window, and requested rotation.
The detailed release audit is retained in the private publication review
package; this repository contains only the public-facing security guidance.
