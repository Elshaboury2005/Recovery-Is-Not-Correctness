# GitHub DOI Linkage Validation

Date: 2026-11-18

Status labels below are literal execution outcomes. `NOT RUN` is not a pass.

## Repository state

| Check | Command | Outcome |
|---|---|---|
| Initial worktree/branch | `git status --short --branch` | PASS — clean `main` before edits |
| Initial commit | `git rev-parse HEAD` | PASS — `24946769d9945c13634ccb0265e12739774fd7e2` |
| Initial remote main | `git ls-remote origin refs/heads/main` | PASS — same SHA as local main |
| Remote URL | `git remote -v` | PASS — requested GitHub repository for fetch/push |

## DOI and dataset verification

| Check | Command | Outcome |
|---|---|---|
| Zenodo record | `curl -sS -L --max-time 25 ... https://zenodo.org/records/24325138` | PASS — HTTP 200; final URL remained the record URL |
| DOI resolver | `curl -sS -L --max-time 30 ... https://doi.org/10.5281/zenodo.24325138` | PASS — HTTP 200; final URL `https://zenodo.org/records/24325138` |
| Record metadata | `rg -n -i 'ChaosFlow|Consolidated Research Evidence|24325138|ChaosFlow_Research_Artifacts_FINAL.zip' /tmp/chaosflow_zenodo_record.html` | PASS — expected title, DOI, ZIP name, public record, and 22-artifact description observed |
| Local validated package | `sha256sum .../ChaosFlow_Research_Artifacts_FINAL.zip` | PASS — `11788da06068a1ab5ebf253d3d9aebd8920d4b549487cc5248d024fa0b4db986` |
| Local package size | `stat -c 'size=%s bytes' .../ChaosFlow_Research_Artifacts_FINAL.zip` | PASS — 517159 bytes, matching the public record file size |

## Documentation and metadata validation

| Check | Command | Outcome |
|---|---|---|
| Markdown relative links/anchors | inline Python Markdown-link checker over tracked `*.md` | PASS — 7 relative links checked; no missing files or anchors |
| Working-tree whitespace | `git diff --check` | PASS |
| Research-artifact manifest | `sha256sum -c research_artifacts/SHA256_MANIFEST.txt` | PASS — 21/21 manifest entries verified |
| Artifact file count | `git ls-files research_artifacts \| wc -l` | PASS — 22 tracked files; the manifest intentionally indexes 21 content files |
| CFF parse | `python3` with PyYAML parsing `CITATION.cff` | PASS — CFF 1.2.0 parsed; software title, creator, and MIT license unchanged |
| MIT consistency | `rg -n '^license: MIT$\|MIT License\|Copyright' LICENSE CITATION.cff README.md` | PASS — MIT license and ChaosFlow Contributors attribution consistent |
| CFF schema validator | `command -v cffconvert; python3` module check | NOT RUN — `cffconvert` and `jsonschema` are not installed; CFF was not extended |

## Secret and privacy checks

| Check | Command | Outcome |
|---|---|---|
| Gitleaks availability | `command -v gitleaks` | NOT RUN — Gitleaks is not installed |
| Equivalent current-tree scan | `rg` high-confidence credential patterns over the current tree | PASS — no matches |
| Equivalent Git-history scan | `git rev-list --all` plus `git grep` high-confidence credential patterns | PASS — no matches in Git history |
| Private-key/credential URL scan | included in the equivalent scan | PASS — no private-key markers or credential-bearing URLs |
| Personal-data marker review | `rg` email/home-path/user-path/private-key markers | REVIEWED — only placeholder `admin@example.com`, container path `/home/appuser`, and a public third-party package-maintainer address were observed; no private contributor address was identified |

## Applicable repository tests

| Check | Command | Outcome |
|---|---|---|
| Research artifact CSV regression test | `docker run --rm -v "$PWD:/workspace:ro" -w /workspace resilient-big-data-platform-backend:latest pytest tests/test_research_artifact_csv.py -q` | PASS — 2 passed |
| Full backend suite in prebuilt local image | `docker run ... resilient-big-data-platform-backend:latest pytest -q -m 'not integration' -rs` | FAIL — prebuilt image lacks `PyJWT`; collection stopped with 27 import errors. This image is stale relative to `backend/requirements.txt` and is not a documentation-only release gate. |
| Fresh backend image build | `docker build -t chaosflow-doi-backend-check backend/` | NOT RUN TO COMPLETION — dependency download stalled during `pip install`; the attempt was cancelled after 63.8 seconds |
| Frontend lint/test/build | `npm run lint`, `npm test`, `npm run build` | NOT RUN — Node/npm and `frontend/node_modules` are unavailable; no frontend files changed |
| Distributed experiments | none | NOT RUN BY DESIGN — explicitly outside this documentation-only scope |

## Workflow and public CI inspection

| Check | Command | Outcome |
|---|---|---|
| Workflow review | `sed -n '1,230p' .github/workflows/ci.yml` | PASS — workflow inspected; CI-only credentials are generated test values, not tracked secrets |
| Existing public CI run | GitHub Actions public API query for run `44165513249` | PASS — prior run on the original main SHA completed successfully |
| Existing public artifact metadata | GitHub Actions public API query | PASS — two non-expired artifact records observed |
| Existing SARIF artifact content | unauthenticated public artifact download | NOT VERIFIED — GitHub returned HTTP 401; no claim is made about its contents |
| CI for the new commit | GitHub Actions after push | PENDING — final result is recorded in `GITHUB_DOI_FINAL_STATUS.md` |

No research result, manuscript, validated Zenodo ZIP, or Git history was
modified by the validation commands.
