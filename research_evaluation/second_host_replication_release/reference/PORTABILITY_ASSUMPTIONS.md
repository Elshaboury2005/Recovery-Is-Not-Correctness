# Portability assumptions and required operator checks

The portable Compose file uses relative paths so the release can live inside the Linux filesystem of WSL2. Keep the release and its runtime state under the WSL2 Linux filesystem, not `/mnt/c`, to reduce bind-mount and metadata problems.

Before execution, the operator must confirm:

- Docker Desktop is running with the WSL2 engine and the selected WSL distribution is integrated.
- At least approximately 16 GB host RAM is available for the declared service limits and Docker overhead.
- WSL2 has enough free disk for images, the dataset, HDFS/Kafka/Postgres state, and run evidence.
- `tc`/`netem` and `NET_ADMIN` work inside the isolated DataNode container for C5.
- Docker socket access from the backend is available and restricted to this campaign project.
- the chosen host ports are free, or the operator documents a reviewed port adjustment everywhere it is needed.
- HDFS checkpoint quarantine/restore (C7) works on the selected Docker Desktop storage backend.

Windows filesystem semantics, Docker Desktop resource limits, clock behavior, and storage pressure can change timings. These are portability risks to validate, not reasons to reinterpret a failed capability check as a scientific result.

