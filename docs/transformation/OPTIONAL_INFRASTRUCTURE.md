# Optional Infrastructure Profiles

## Baseline decision

The existing core Compose path remains the default. Flink and Hive services are profile-gated so a normal core deployment does not require either optional technology.

The configured image references are:

- Flink: `flink:1.20.1-scala_2.12-java17`
- Hive: `apache/hive:4.0.0`

These are explicit image references, not `latest` tags. The Apache Flink documentation recommends explicit tags containing the Flink and Scala versions, and Apache Hive documents the `apache/hive:4.0.0` image and `SERVICE_NAME` startup modes. The exact interoperability of Hive 4.0.0 with the repository's Hadoop 3.2.1 image remains a Phase 8 verification item.

## Profiles

```bash
# Existing core path (unchanged service behavior)
docker compose up -d

# Add Flink JobManager and TaskManager
docker compose --profile flink up -d

# Add Hive Metastore and HiveServer2
docker compose --profile hive up -d

# Add both optional integrations
docker compose --profile full up -d
```

`core` is the documented default path: Compose services without a profile are always active, so `docker compose up -d` remains backward compatible. The `full` profile activates both optional groups in addition to the core services.

## Service boundaries

| Service | Profile | Host endpoint | Current role |
|---|---|---|---|
| `flink-jobmanager` | `flink`, `full` | `localhost:8082` | Flink REST/UI and job manager |
| `flink-taskmanager` | `flink`, `full` | internal | Flink task execution |
| `hive-metastore` | `hive`, `full` | `localhost:9083` | Hive Thrift metastore using persistent local Derby data |
| `hive-server` | `hive`, `full` | `localhost:10000`, `localhost:10002` | HiveServer2 SQL endpoint and web UI |

The optional services share the existing `platform-network`, Kafka/HDFS dependencies, and stable service names. Flink checkpoints use a separate named volume and are not assumed to be portable to Spark.

## Verification status

- Compose syntax and profile rendering must pass before a profile is used.
- Flink image pull/startup and REST health must be verified in Phase 1.
- Hive metastore/server startup, HDFS warehouse access, Parquet table registration, and SQL execution are Phase 8 gates.
- No optional service is reported by the core readiness endpoint until a capability-aware health API is implemented.

## Resource guidance

The optional profile adds at least one JVM process per service pair. Start the core stack first, then enable one optional profile at a time on constrained WSL2 environments. Do not remove or recreate existing volumes to enable these profiles.
