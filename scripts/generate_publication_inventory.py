#!/usr/bin/env python3
"""Generate storage and duplicate inventories without changing source evidence.

The inventory deliberately treats research evidence and Git internals as
protected.  It hashes regular files outside ``.git`` so duplicate findings are
content-based rather than name-based.  Generated reports are replaceable and
should be regenerated after any approved cleanup or archival relocation.
"""

from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SKIP_HASH_PREFIXES = {".git"}
HASH_CHUNK = 1024 * 1024


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def category(path: Path) -> tuple[str, str, str, str, str, str]:
    rel = relative(path)
    parts = set(path.relative_to(ROOT).parts)
    name = path.name
    if ".git" in parts:
        return ("E", "no", "no", "unknown", "none", "Git internals are protected")
    if name in {".env", "node_modules"} or "node_modules" in parts:
        return ("E", "no", "no", "unknown", "none", "User/dependency environment; do not remove automatically")
    if name == ".p3c-ivy-cache" or ".p3c-ivy-cache" in parts:
        return ("D", "yes", "no", "no", "size", "Regenerable Spark/Ivy dependency cache")
    if "__pycache__" in parts or ".pytest_cache" in parts:
        return ("D", "yes", "no", "no", "size", "Regenerable interpreter/test cache")
    if rel.startswith("research_evaluation/"):
        return ("B", "no", "yes", "unknown", "review", "Historical or current scientific evidence; preserve")
    if rel.startswith(("backend/", "frontend/", "spark-jobs/", "airflow/", "infrastructure/", "tests/", "scripts/", "docs/", "experiments/")):
        return ("A", "no", "no", "yes", "none", "Project source, test, configuration, or documentation")
    if name.endswith((".log", ".tmp", ".bak")):
        return ("D", "yes", "unknown", "no", "size", "Generated local output; verify before removal")
    return ("E", "unknown", "unknown", "unknown", "review", "Unclassified or user-owned path")


def files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if ".git" in path.relative_to(ROOT).parts:
            continue
        result.append(path)
    return result


def digest(path: Path) -> tuple[str, int, str]:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(HASH_CHUNK):
                hasher.update(chunk)
        return (relative(path), path.stat().st_size, hasher.hexdigest())
    except OSError as exc:
        return (relative(path), -1, f"ERROR:{exc.__class__.__name__}")


def directory_bytes(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    inventory_files = files()
    hashed = {}
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        for rel, size, sha in pool.map(digest, inventory_files):
            hashed[rel] = (size, sha)

    now = datetime.now(timezone.utc).isoformat()
    records: list[list[object]] = []
    for path in sorted(inventory_files, key=lambda item: relative(item)):
        rel = relative(path)
        size, sha = hashed[rel]
        cat, reproducible, evidence, in_use, action, reason = category(path)
        records.append([rel, size, sha, cat, reproducible, in_use, evidence, action, size if action == "size" else 0, "low" if cat == "D" else "review", reason])

    write_csv(
        REPORTS / "STORAGE_INVENTORY.csv",
        ["path", "size_bytes", "sha256", "category", "reproducible", "used_by_current_code", "published_scientific_evidence", "proposed_action", "expected_recoverable_bytes", "risk_level", "reason"],
        records,
    )

    largest = sorted(records, key=lambda row: int(row[1]), reverse=True)[:250]
    write_csv(REPORTS / "LARGEST_FILES.csv", ["path", "size_bytes", "sha256", "category", "reason"], [[row[0], row[1], row[2], row[3], row[10]] for row in largest])

    groups: dict[tuple[int, str], list[str]] = defaultdict(list)
    for rel, (size, sha) in hashed.items():
        if size >= 0 and not sha.startswith("ERROR:"):
            groups[(size, sha)].append(rel)
    duplicate_rows: list[list[object]] = []
    for (size, sha), paths in sorted(groups.items(), key=lambda item: (-item[0][0], item[0][1])):
        if len(paths) < 2:
            continue
        canonical = min(paths, key=lambda item: (len(Path(item).parts), len(item), item))
        for duplicate in sorted(paths):
            if duplicate == canonical:
                continue
            duplicate_rows.append([sha, size, canonical, duplicate, "verified_identical_bytes", "retain until approved archival/removal", "medium"])
    write_csv(REPORTS / "DUPLICATE_FILES.csv", ["sha256", "size_bytes", "canonical_path", "duplicate_path", "verification", "proposed_action", "risk_level"], duplicate_rows)

    candidate_rows: list[list[object]] = []
    candidate_dirs = []
    for path in ROOT.rglob("*"):
        if not path.is_dir() or path.is_symlink():
            continue
        rel = relative(path)
        if path.name in {"__pycache__", ".pytest_cache", ".p3c-ivy-cache"}:
            candidate_dirs.append(path)
    for path in sorted(candidate_dirs, key=lambda item: relative(item)):
        size = directory_bytes(path)
        candidate_rows.append([relative(path), size, "directory", "yes", "no", "no", "remove only after no active process is confirmed", size, "low", "Regenerable cache; not scientific evidence"])
    write_csv(REPORTS / "CLEANUP_CANDIDATES.csv", ["path", "size_bytes", "file_category", "reproducible", "used_by_current_code", "published_scientific_evidence", "proposed_action", "expected_recoverable_bytes", "risk_level", "reason"], candidate_rows)

    repo_bytes = directory_bytes(ROOT)
    research_bytes = directory_bytes(ROOT / "research_evaluation")
    git_bytes = directory_bytes(ROOT / ".git")
    cache_bytes = directory_bytes(ROOT / ".p3c-ivy-cache")
    reports = REPORTS / "STORAGE_ANALYSIS.md"
    reports.write_text(
        f"# Storage analysis\n\nGenerated: `{now}`\n\n"
        "This inventory is content-hash based for regular files outside `.git`. Historical research evidence, the Git object database, Docker volumes, and uncertain user files are protected.\n\n"
        f"| Scope | Bytes |\n|---|---:|\n| Repository worktree including generated outputs | {repo_bytes} |\n| `research_evaluation/` | {research_bytes} |\n| `.git/` | {git_bytes} |\n| `.p3c-ivy-cache/` | {cache_bytes} |\n| Hashed regular files outside `.git` | {len(inventory_files)} |\n| Verified duplicate rows | {len(duplicate_rows)} |\n| Regenerable cache candidates | {len(candidate_rows)} |\n\n"
        "Duplicate reports identify byte-identical content only; filename similarity is never treated as proof. A duplicate under a historical evidence package remains protected until its preservation mapping and an explicit deletion approval exist.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
