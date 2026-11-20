# ChaosFlow 240-run second-host replication release

This directory is a **replication release**, not a copy of the primary campaign evidence. It contains the frozen protocol, portable runner, source snapshot, build inputs, planned schedules, and validation documentation needed to perform an independent 240-qualifying-run campaign on a Windows 11 host using WSL2 and Docker Desktop.

Status at packaging: **PARTIALLY_READY**. The protocol and operational runner are present and the package is designed to be independently executed, but the exact final repaired source is preserved as a campaign-local frozen snapshot rather than as a single Git commit. The dataset is also intentionally not bundled.

No experiment, fault injection, Docker Compose startup, or live service validation is performed by the release builder.

## Start here

1. Read [START_HERE_SECOND_HOST.md](START_HERE_SECOND_HOST.md).
2. Read [SECOND_HOST_EXECUTION_PLAN.md](SECOND_HOST_EXECUTION_PLAN.md) and [SECOND_HOST_PORTABILITY_REPORT.md](SECOND_HOST_PORTABILITY_REPORT.md).
3. Acquire the exact dataset described in `dataset/DATASET_ACQUISITION.md` and verify its SHA-256 before creating `.env`.
4. Follow the staged validation sequence in `SECOND_HOST_VALIDATION_REPORT.md`.
5. Run the main campaign only after the operator has independently approved the WSL2/Docker capability checks.

The original primary evidence and its raw data are outside this release and are not required to be copied to the second host. Do not merge historical result files into the planned schedules.

