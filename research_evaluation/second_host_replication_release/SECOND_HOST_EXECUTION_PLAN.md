# Second-host execution plan

## Phase 0 — prepare

Use WSL2 Linux storage, confirm Docker Desktop integration, reserve the release directory, acquire and hash the exact dataset, and create `.env` from `.env.example` with operator-supplied secrets. Keep the original ZIP and primary campaign read-only.

## Phase 1 — static validation

Run the checks listed in `SECOND_HOST_VALIDATION_REPORT.md`. These checks must not start services. Resolve syntax, Compose interpolation, path, dependency, and secret-scan failures before any startup.

## Phase 2 — capability validation

With an explicit operator decision, bring up only the fresh project `chaosflow-240-replication`, validate health and isolation, then verify C5's DataNode `NET_ADMIN`/`tc netem` capability and C7's checkpoint path behavior. Record the host, Docker Desktop, WSL2, image, and capability details in a local validation log. Tear down only this new project if the capability check fails; never touch historical projects.

## Phase 3 — pilot

Run the pilot protocol and adjudicate it using the frozen rules. A failed pilot blocks the main campaign until the cause is understood and the protocol owner approves a documented correction.

## Phase 4 — main campaign

Run `run_240_campaign.py` with the planned schedule. Preserve all attempts, including invalid attempts and replacements. The campaign target is 240 qualifying runs, not 240 process invocations. Do not manually edit statuses or metrics.

## Phase 5 — analysis and archive

Run analysis only after the campaign has reached the target and the evidence ledger passes validation. Record the dataset hash, source tree fingerprint, Compose/image digests, host capability results, invalid-attempt ledger, and analysis outputs in a new second-host evidence directory. Never overwrite the primary evidence directory.

