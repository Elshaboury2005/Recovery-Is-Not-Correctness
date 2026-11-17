# Reproducibility

Reproduction is layered. A reader can verify the derived research package
without starting Docker, then reproduce application tests in an isolated
Compose environment.

## Verify the local artifact

```bash
python3 scripts/generate_publication_inventory.py
sha256sum -c research_artifacts/SHA256_MANIFEST.txt
```

The inventory script may be rerun after cleanup. Its duplicate report is based
on SHA-256 and does not decide deletion.

## Verify the application

```bash
docker compose config --quiet
docker exec platform-backend pytest -q -m 'not integration'
cd frontend && npm ci && npm run lint && npm test -- --run && npm run build
```

The frontend commands require a Node/npm toolchain. If it is unavailable, the
result is `NOT_EXECUTED_TOOL_UNAVAILABLE`, not a pass.

## Verify the scientific correction

The compact tables and correction map in `research_artifacts/` are the
repository-level scientific record. The preserved-log classification tests and
large raw evidence tree are maintained in the separate review/archive package,
not duplicated in this GitHub source candidate. Those tests exercise
classification and preserved evidence only; they do not inject a live fault.

## Reproduce a campaign

Use a fresh isolated host or Compose project, freeze the relevant protocol from
`research_artifacts/protocols/`, capture host/container metadata, and follow
the campaign-specific scripts in the separately archived evidence package. Do
not reuse the running shared services or delete their volumes.
