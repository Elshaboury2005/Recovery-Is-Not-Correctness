# GitHub DOI Linkage Changelog

Date: 2026-11-18

## Scope

This change updates the existing GitHub repository's publication-status
documentation only. It does not alter research results, the validated Zenodo
archive, manuscript content, author order, repository visibility, or Git
history.

## Files changed

- `README.md`
- `research_artifacts/README.md`
- `research_artifacts/SHA256_MANIFEST.txt` (the checksum for the changed README)
- `GITHUB_DOI_CHANGELOG.md`
- `GITHUB_DOI_VALIDATION.md`
- `GITHUB_DOI_FINAL_STATUS.md`
- `GITHUB_DOI_DOCUMENTATION_BUNDLE.zip`

`CITATION.cff` and `LICENSE` were inspected and intentionally left unchanged.
The software citation remains attributed to **ChaosFlow Contributors**, with
the existing title, ordering, MIT license, and copyright attribution.

## Documentation changes

### Root `README.md`

Original publication-status text:

> No DOI or public Zenodo URL has been assigned. The separate Zenodo artifact
> must not be inferred from this repository and is not uploaded by this release
> preparation.

New publication-status text:

> The curated, checksum-indexed public evidence is published separately as the
> Zenodo dataset **ChaosFlow: Configuration-Driven Resilient Big Data Pipeline
> Platform — Consolidated Research Evidence**, with version DOI
> **10.5281/zenodo.24325138**. The deposited file is
> `ChaosFlow_Research_Artifacts_FINAL.zip` with the published package SHA-256.
> Full private campaign logs are not part of the public deposit, synthetic
> E1--E8 planning material is excluded, and the deposit makes no claim of full
> independent-host reproduction, physical durable-media commit, or universal
> exactly-once behavior.

The README also contains the exact copyable dataset citation and clickable
record/DOI links.

### `research_artifacts/README.md`

Original publication-status text:

> No external upload or DOI was created. Publication remains subject to author,
> supervisor, licensing, and repository-approval decisions.

New publication-status text identifies the verified public Zenodo record and
DOI, while preserving the private-log and synthetic-planning-material caveats.
The corresponding manifest entry was updated to the SHA-256 of this changed
documentation file; all other manifest entries remain unchanged.

## Dataset linkage

- Record: <https://zenodo.org/records/24325138>
- Version DOI: <https://doi.org/10.5281/zenodo.24325138>
- File: `ChaosFlow_Research_Artifacts_FINAL.zip`
- Package SHA-256: `11788da06068a1ab5ebf253d3d9aebd8920d4b549487cc5248d024fa0b4db986`
- Public record title: `ChaosFlow: Configuration-Driven Resilient Big Data Pipeline Platform — Consolidated Research Evidence`

The record resolved from this host with HTTP 200, exposed the expected title,
DOI, public ZIP filename, and 22-artifact description. The local validated ZIP
was not edited or re-uploaded.

## CFF decision

`CITATION.cff` parses as YAML and its software metadata is unchanged. A
`cffconvert`/CFF schema validator was not installed in this environment, so no
new related-dataset field was added. The dataset citation is therefore placed
in `README.md` and the research-artifact README, without replacing the
software's primary citation.

## Validation and unresolved items

The exact commands and outcomes are recorded in
[`GITHUB_DOI_VALIDATION.md`](GITHUB_DOI_VALIDATION.md). The local documentation,
manifest, equivalent secret scan, Markdown-link check, artifact ZIP checksum,
and applicable research-artifact test passed. The full GitHub workflow was not
run locally: the host has no Node/npm, and the prebuilt backend image used for
an extra full-suite attempt lacks the current `PyJWT` dependency. This is an
environmental validation limitation, not a change to the research or software
source. The public CI result after the final push is recorded in
`GITHUB_DOI_FINAL_STATUS.md`.
