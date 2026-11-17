# Contributing

Contributions should be small, reviewable, and reproducible.

## Before opening a change

- Read the relevant architecture and configuration documentation.
- Do not include `.env`, credentials, Docker volume exports, raw research logs,
  or generated dependency directories.
- Add or update tests for changed behavior.
- Run backend tests for backend changes and the frontend lint/test/build suite
  for frontend changes.
- Record any protocol or evidence-schema change with a new version; do not
  rewrite historical raw evidence.

## Research changes

Every result must map to an authoritative raw evidence location and a protocol
version. Preserve all-attempt accounting, including invalid, incomplete,
failed-closed, and unknown attempts. Exact correctness uses the typed full-row
multiset oracle and the fixture's legitimate multiplicities.

## Review checklist

- No hardcoded machine-specific paths or secrets.
- No unbounded file preview/download behavior.
- No destructive Docker or Git commands in automation.
- Documentation commands work from a clean clone.
- Generated artifacts are reproducible and checksum manifests are updated.
