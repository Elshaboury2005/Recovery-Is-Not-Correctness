# Consolidated research artifacts

This is the canonical, storage-efficient research summary for ChaosFlow. It
contains small machine-readable result tables, protocol indexes, correction
maps, provenance, limitations, and checksums. It does not duplicate the
multi-gigabyte historical evidence tree.

## Evidence policy

Original raw observations and historical archives remain unchanged under
`research_evaluation/`. The authoritative current correction package is:

`research_evaluation/chaosflow_research_final_resource_aware_completion_20261116_r2_scientific_classification_correction/`

The package's R2 ZIP, sidecar, and validation manifest are preserved at that
path. The catalog below maps every consolidated claim to its evidence source;
the correction map changes claim interpretation only and never rewrites a raw
file.

## Layout

The subdirectories are organized by scientific population. Their READMEs point
to the authoritative local evidence rather than copying it. The CSV files in
this directory are the compact release tables intended for GitHub review and
Zenodo metadata assembly.

`UNKNOWN`, `INCOMPLETE`, `INVALID`, `FAILED_CLOSED`, and `NOT_OBSERVABLE` are
meaningful states. They are never encoded as numeric zero.

## Verification

```bash
sha256sum -c SHA256_MANIFEST.txt
```

No external upload or DOI was created. Publication remains subject to author,
supervisor, licensing, and repository-approval decisions.
