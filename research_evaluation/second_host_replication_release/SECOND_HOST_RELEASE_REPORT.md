# Second-host replication release report

## Overall status: PARTIALLY_READY

The release is assembled in an isolated staging directory and is intended to be independently executable after the target operator supplies the exact dataset and secrets and completes the target-host capability checks. Experiments were not run during preparation.

## Included

- frozen protocol, qualification rules, power analysis, original schedule references, and clean 240/16-row planned schedules;
- campaign runner, observer worker, dashboard/supervisor source, frozen application/Spark source snapshot, and Docker build inputs;
- portable Compose file with relative state/data paths and a fresh project name;
- dataset acquisition instructions and hash contract;
- portability, validation, execution, sample-size, and provenance reports;
- machine-readable baseline manifest, file inventory, SHA-256 manifest, and transfer ZIP sidecar.

## Explicit limitations

The final repaired source snapshot was produced locally during the primary campaign and is not represented by one exact Git commit. The repository baseline commit and every included source fingerprint are recorded in `REPLICATION_BASELINE_MANIFEST.json`, including the differences from the initial preflight fingerprints. Backend Dockerfile/requirements build inputs were copied from the current worktree because they were not part of the frozen source snapshot; their hashes are recorded and this is an exact-build-context limitation.

The dataset and primary raw evidence are not included. The second host must acquire the exact dataset independently. Windows 11/WSL2 runtime equivalence, C5, C6, C7, Docker socket isolation, and resource/port behavior remain unverified until the target host performs the checks in `SECOND_HOST_VALIDATION_REPORT.md`.

