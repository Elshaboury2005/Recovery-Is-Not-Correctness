"""Regression checks for the public research-artifact CSV indexes."""

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_csv(name: str) -> list[dict[str, str]]:
    path = REPO_ROOT / "research_artifacts" / name
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    return rows


def test_correction_supersession_map_has_quoted_c003_scope_note() -> None:
    rows = _read_csv("CORRECTION_SUPERSESSION_MAP.csv")
    row = next(item for item in rows if item["correction_id"] == "C003")
    assert row["scope_note"] == "Correction changes interpretation, not the raw CSV."
    assert len(row) == 7
    assert len(rows) == 8


def test_evidence_catalog_has_quoted_e007_notes() -> None:
    rows = _read_csv("EVIDENCE_CATALOG.csv")
    row = next(item for item in rows if item["claim_id"] == "E007")
    assert row["notes"] == "R2 outlier is source-incomplete, not recovered-incorrect."
    assert len(row) == 9
    assert len(rows) == 12
