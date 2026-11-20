# Second-host validation report

## Release-builder checks

The following checks are required and are performed on the packaged release without starting experiments: Python syntax compilation; Compose interpolation/configuration rendering with a temporary `.env`; runner `--help`; file inventory and hash verification after ZIP extraction; duplicate/symlink checks; and secret scanning. No `docker compose up`, fault injection, or campaign supervisor execution is part of release validation.

## Target-host checks still required

The receiving operator must record pass/fail evidence for:

1. WSL2 Linux filesystem placement and free space.
2. Docker Desktop WSL2 integration and resource allocation.
3. exact dataset SHA-256 and input/output contract.
4. fresh Compose project health and container-name isolation.
5. backend Docker socket access limited to the fresh project.
6. C5 `tc qdisc`/`netem` and `NET_ADMIN` inside the DataNode.
7. C6 bounded storage pressure and cleanup behavior.
8. C7 checkpoint metadata quarantine/restore and post-fault validation.
9. pilot qualification and baseline stability.

Until those checks pass, the release is not a claim that Windows 11 is scientifically equivalent to the primary Linux environment.

