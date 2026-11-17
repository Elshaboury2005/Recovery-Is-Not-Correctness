# Research reproducibility

The compact artifact is reproducible from the current worktree without copying
the 9+ GiB evidence tree. Start with the protocol index and claim catalog, then
inspect the referenced authoritative package. Preserve the paths because the
raw logs and ZIP sidecars are checksum-anchored historical evidence.

```bash
sha256sum -c research_artifacts/SHA256_MANIFEST.txt
python3 scripts/generate_publication_inventory.py
```

For application validation, use `docker compose config --quiet` and the backend
test command in `REPRODUCIBILITY.md`. For correction validation, run the local
classification and preserved-log tests in the latest R2 correction package with
pytest available. Do not start a live fault campaign to validate documentation.

All result tables use explicit text states for missing endpoints. An empty
recovery time means `NOT_REPORTED` or `NOT_OBSERVABLE`, not zero seconds.
