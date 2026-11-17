# Current Blockers and Limitations

## Active blockers

### Host development tools unavailable

The host environment currently has Docker and Docker Compose, but no `python`, `pytest`, `node`, or `npm` executables. Backend verification is possible through the existing backend container. Frontend verification is currently handled through the cached Node-capable evaluation image; direct host tooling remains unavailable.

### Optional Flink/Hive runtime verification pending

Profile-gated Flink and Hive services/configuration now exist, and backend engine contracts are additive. Actual image startup, Flink artifact submission, Hive metastore initialization, and Hive query execution are still unverified.

### Hive client driver unavailable

The live backend reports `Hive client driver is not installed in the backend image`; the read-only SQL API therefore records explicit failed query evidence until the driver and HiveServer2 runtime are available.

### Docker registry access unavailable

Phase 1 profile rendering passes, but the first Flink startup attempt could not resolve the explicit image because the Docker daemon had no network route to Docker Hub. This is an environment blocker, not evidence that the Compose configuration or image is compatible. Retry service startup when registry access is available.

The same registry route blocks rebuilding the production frontend image because its Dockerfile resolves `node:20-alpine` and `nginx:alpine`. The source-level frontend build remains verified in the cached Node evaluation image, but the already-running production frontend container has not been replaced. A fresh retry on 2026-11-06 also failed for `flink:1.20.1-scala_2.12-java17` and `apache/hive:4.0.0` with `connect: network is unreachable`; no optional container was created.

### Flink benchmark parity and artifact packaging

The Flink adapter deliberately refuses to submit without a verified Kafka/HDFS job artifact and never falls back to Spark. Until the optional Flink runtime and artifact are available, Spark/Flink comparisons cannot be treated as measured parity.

### Benchmark resource sampling and broad correctness coverage

Benchmark campaigns record requested resources and explicit `not_measured` utilization fields. The current live Spark path has independent correctness for supported finite CSV contracts; unsupported contracts remain `UNKNOWN` rather than being ranked.

### Recommendation overrides and multi-engine evidence

Recommendations persist generated evidence and tradeoffs, and safe reconfiguration now records explicit overrides and an audit trail. The live isolated verification path records requested overrides but does not mutate production routing. Only Spark has live correctness-passed evidence in this environment, so the recommender cannot establish a measured Flink comparison.

### Phase 12 production-image follow-up

The new authenticated frontend routes have passed TypeScript, production build, unit/accessibility tests, lint, and real-browser source smoke. The complete supported Spark profile→classification→benchmark→recommendation→reconfiguration workflow has also passed live, including isolated correctness verification, rollback, and post-rollback health. The cached Node image still has no bundled Chromium for its standard launcher, so the reproducible browser command uses host Chrome through CDP; the source-level browser gate is complete.

The production frontend image has not been refreshed because its Dockerfile requires `node:20-alpine` and `nginx:alpine` from Docker Hub. Retry the image build when registry access is restored; do not replace the currently running image with an unverified substitute.

The new `transformation_intelligence_dag` is parsed by the live Airflow scheduler with seven tasks and no import errors. It has not been triggered in this session because doing so would create a duplicate benchmark/reconfiguration demonstration; use a controlled `dag_run.conf` when an Airflow execution acceptance window is available.

## Constraints

- The worktree contains pre-existing tracked and untracked changes, including research-evaluation material. They must be preserved.
- Running research containers and persistent service volumes are active. Destructive Compose commands are out of scope.
- The original pipeline-flow visualization remains preserved alongside the new deployed infrastructure topology explorer.
