# Second-host portability report

## Assessment

The release is **portable in layout and intended workflow**, but not yet proven equivalent on Windows 11/WSL2/Docker Desktop. The release builder did not start Docker or run experiments, so runtime capability remains a second-host validation responsibility.

## Main risks

| area | assessment | required action |
|---|---|---|
| relative bind mounts | addressed in portable Compose | keep release in WSL2 Linux storage; run Compose from that path |
| dataset identity | not bundled | acquire exact hash-matching file; hard stop on mismatch |
| C5 `tc/netem` | unverified on target host | verify `NET_ADMIN`, `tc`, and isolated DataNode behavior before pilot |
| C6 storage pressure | host-filesystem dependent | document Docker/WSL2 free space and verify bounded pressure semantics |
| C7 checkpoint path | host/storage dependent | verify quarantine/restore on the second host |
| Docker socket | required by fault controller | confirm backend can inspect/control only the campaign project |
| ports/resources | not probed here | check ports and Docker memory/disk allocation before startup |
| images/dependencies | build and pulls not run here | record image digests and dependency installation results on target host |

The original Linux Compose file is retained for provenance; the portable Compose file is the execution candidate. It replaces hard-coded host paths and uses a campaign-specific project name, but it does not eliminate platform-specific kernel or Docker Desktop behavior.

