# Start here: second-host replication

## Scope

This release prepares an independent rerun of the ChaosFlow 240-run study. It does not run the study and does not include the primary raw evidence or the dataset bytes.

## Required order

1. Use WSL2 and place this directory in the Linux filesystem.
2. Read the release, portability, execution, and validation reports.
3. Acquire `dataset/sales_large.csv` through an approved channel and verify the required SHA-256.
4. Copy `.env.example` to `.env`; set unique local `POSTGRES_PASSWORD` and `ADMIN_PASSWORD` values and a non-empty `JWT_SECRET_KEY`.
5. Run only the static checks first: `python3 -m py_compile`, `docker compose config --quiet`, and the runner's `--help`.
6. Perform the explicit Docker Desktop/WSL2 capability checks, including C5 and C7. Record failures as portability blockers.
7. Obtain human approval to start the campaign. The runner is sequential and resumable; preserve its generated schedules and evidence.
8. After 240 qualifying runs, run the supplied analysis against the second-host evidence and archive its manifest separately from the primary campaign.

Do not run `campaign_supervisor.py --help`: that script has no help-only mode and may perform supervisory actions. Do not reuse a historical Compose project or historical volumes.

