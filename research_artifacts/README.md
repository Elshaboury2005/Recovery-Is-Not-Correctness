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
the separately published Zenodo dataset.

`UNKNOWN`, `INCOMPLETE`, `INVALID`, `FAILED_CLOSED`, and `NOT_OBSERVABLE` are
meaningful states. They are never encoded as numeric zero.

## Verification

```bash
sha256sum -c SHA256_MANIFEST.txt
```

The curated public package is published separately as the Zenodo dataset
[`ChaosFlow: Configuration-Driven Resilient Big Data Pipeline Platform —
Consolidated Research Evidence`](https://zenodo.org/records/24325138), with
version DOI [`10.5281/zenodo.24325138`](https://doi.org/10.5281/zenodo.24325138).
The public deposit contains checksum-indexed evidence; full private campaign
logs are not part of the public deposit, and synthetic E1--E8 planning material
is excluded from the public archive.
