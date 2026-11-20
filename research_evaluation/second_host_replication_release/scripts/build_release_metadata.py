#!/usr/bin/env python3
"""Build deterministic release metadata and a sanitized transfer archive.

This script never starts Docker or runs a campaign. It refuses to package a
dataset CSV, .env, runtime state, symlink, or private-key material.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
ARCHIVE = PARENT / "ChaosFlow_240_SecondHost_Replication_Transfer.zip"
SIDECAR = PARENT / "ChaosFlow_240_SecondHost_Replication_Transfer.zip.sha256"
BASELINE_COMMIT = "fba8b9d4656cda85ee0a49b468e2bf2dd837dadb"
DATASET_SHA256 = "bff70d62204d7d53eda5f3d4a9696b9d39be7f43c0f104e09a4f3b30a122c867"

EXCLUDE_NAMES = {
    ".env",
}
EXCLUDE_SUFFIXES = {".zip", ".pyc"}
EXCLUDE_PARTS = {"__pycache__", ".git"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)postgres(?:ql)?://[^\s/]+:[^\s@]+@"),
    re.compile(r"(?m)^(?:POSTGRES_PASSWORD|ADMIN_PASSWORD|JWT_SECRET_KEY|GRAFANA_ADMIN_PASSWORD)\s*=\s*[^#\s].*$"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDE_PARTS for part in relative.parts):
        return True
    if path.name in EXCLUDE_NAMES or path.suffix in EXCLUDE_SUFFIXES:
        return True
    if path.name == "sales_large.csv":
        return True
    if path == ARCHIVE or path == SIDECAR or path.name == ARCHIVE.name:
        return True
    return False


def release_files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        if path.is_file() and not excluded(path):
            result.append(path)
    return sorted(result, key=rel)


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted((p for p in (ROOT / "source_snapshot").rglob("*") if p.is_file()),
                       key=lambda p: p.relative_to(ROOT).as_posix()):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def scan_secrets(files: list[Path]) -> list[dict[str, str]]:
    hits = []
    for path in files:
        if path == Path(__file__).resolve():
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line) and not line.lstrip().startswith("#"):
                    hits.append({"file": rel(path), "line": str(number), "pattern": pattern.pattern})
    return hits


def write_manifest(files: list[Path]) -> None:
    manifest = {
        "release": "ChaosFlow_240_SecondHost_Replication_Transfer",
        "release_status": "PARTIALLY_READY",
        "created_by": "scripts/build_release_metadata.py",
        "experiments_executed_during_release_build": False,
        "primary_campaign": {
            "campaign_id": "ChaosFlow Research Campaign",
            "protocol_id": "CHAOSFLOW-240-OBSERVER-RECOVERY-V1",
            "baseline_commit": BASELINE_COMMIT,
            "repository": "https://github.com/Mohamed-Abdelaty/Grad.git",
            "target": "240 qualifying runs; 8 scenarios x 2 observer states x 15 repetitions",
            "random_seed": 20261120,
            "attempts": 256,
            "qualifying_runs": 240,
            "invalid_attempts": 16,
            "invalid_attempt_policy": "excluded from qualifying sample and replaced under frozen adjudication rules",
        },
        "dataset_contract": {
            "path": "dataset/sales_large.csv",
            "sha256": DATASET_SHA256,
            "input_rows": 1000000,
            "expected_output_occurrences": 966002,
            "bundled": False,
            "acquisition": "dataset/DATASET_ACQUISITION.md",
        },
        "protocol": {
            "reference": "reference/frozen_protocol.md",
            "qualification": "reference/qualification_adjudication.md",
            "scenarios": ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"],
            "observer_states": ["OBSERVER_ON", "OBSERVER_OFF"],
            "repetitions_per_cell": 15,
            "sequential": True,
        },
        "source_provenance": {
            "source_snapshot_path": "source_snapshot",
            "source_snapshot_tree_sha256": source_fingerprint(),
            "baseline_status": "RECONSTRUCTED_FROM_FROZEN_LOCAL_SOURCE_SNAPSHOT; EXACT_FINAL_SOURCE_COMMIT_UNAVAILABLE",
            "initial_preflight_source_hashes": {
                "experiment_runner.py": "30fd6f2634314220b419d34e28f4f25061b39a6dfc3a4020fcb60863a193faab",
                "recovery_observer.py": "c5b8806c655f2c41b4616fa1967e738599d654cd00f28d2efebf1854720945df",
                "recovery_timeline.py": "12bd9187e98e41f6677bfbc102a81841b1e38c0f68dccda01108c0cc9393029d",
                "docker_controller.py": "b67303352a24b80540dc6d2ffe0c549b0df0a35a30ecd65d8b9184d5633b6144",
                "data_consistency_validator.py": "db89c3a266b029858ff1f213ee26e3d3ce3d85f85e0e3fa9df4c12fa0c18db8d",
                "streaming_processing_job.py": "b9b9603d821f0e39963059d2a3a5ddd200ab650f9603fc1762eea09429e068bd",
            },
            "final_frozen_source_hashes": {
                "experiment_runner.py": "84196979cac6e1968b71a5f145d1ce6194a53c24bf658593f41203939b29f4d0",
                "recovery_observer.py": "31a3a2365c7e32c62d2264e777a807f1968b622be0e46d1d0301ff1443b5f685",
                "recovery_timeline.py": "12bd9187e98e41f6677bfbc102a81841b1e38c0f68dccda01108c0cc9393029d",
                "docker_controller.py": "b67303352a24b80540dc6d2ffe0c549b0df0a35a30ecd65d8b9184d5633b6144",
                "data_consistency_validator.py": "db89c3a266b029858ff1f213ee26e3d3ce3d85f85e0e3fa9df4c12fa0c18db8d",
                "streaming_processing_job.py": "b9b9603d821f0e39963059d2a3a5ddd200ab650f9603fc1762eea09429e068bd",
                "sales_output_oracle.py": "188485eb17f31bf4b19c75db4cd4636f9418c425454d6bc83adcf4151912a40a",
            },
            "campaign_runner_sha256": sha256(ROOT / "run_240_campaign.py"),
            "campaign_supervisor_sha256": sha256(ROOT / "campaign_supervisor.py"),
            "dashboard_sha256": sha256(ROOT / "campaign_dashboard.py"),
            "observer_worker_sha256": sha256(ROOT / "observer_worker.py"),
            "backend_build_inputs": {
                "Dockerfile_sha256": sha256(ROOT / "backend/Dockerfile"),
                "requirements_sha256": sha256(ROOT / "backend/requirements.txt"),
                "note": "copied from current worktree; not present in frozen source snapshot",
            },
        },
        "images": {
            "backend": "local build; primary observed digest sha256:54b204110b280ee2e228a1afb10c4290d64f38ab3a07a8573f95105212974b8f",
            "spark": "bitnamilegacy/spark:3.5.0; primary observed digest sha256:68f45b8ea3e32ce1286d16996e50970dbd7182f5a6b26c014196825cb0f4ece9",
            "namenode": "bde2020/hadoop-namenode:2.0.0-hadoop3.2.1-java8; primary observed digest sha256:51ad9293ec52083c5003ef0aaab00c3dd7d6335ddf495cc1257f97a272cab4c0",
            "kafka": "confluentinc/cp-kafka:7.6.0; primary observed digest sha256:24cdd3a7fa89d2bed150560ebea81ff1943badfa61e51d66bb541a6b0d7fb047",
            "postgres": "postgres:16-alpine; target host must record resolved digest",
        },
        "portability": {
            "platform_target": "Windows 11 / WSL2 / Docker Desktop / approximately 16 GB RAM",
            "compose": "compose.chaosflow-240.yml",
            "project": "chaosflow-240-replication",
            "unverified_capabilities": ["C5 tc/netem + NET_ADMIN", "C6 storage pressure", "C7 checkpoint quarantine/restore", "Docker socket isolation", "target resource and port behavior"],
        },
        "included_file_count": len(files),
        "excluded_from_public_release": ["dataset/sales_large.csv", ".env", "runtime state", "primary raw evidence", "transfer ZIP itself"],
    }
    (ROOT / "REPLICATION_BASELINE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_inventory(files: list[Path]) -> None:
    rows = [{"path": rel(p), "bytes": p.stat().st_size, "sha256": sha256(p), "category": "release"} for p in files]
    with (ROOT / "TRANSFER_FILE_INVENTORY.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "bytes", "sha256", "category"])
        writer.writeheader()
        writer.writerows(rows)


def write_checksums(files: list[Path]) -> None:
    lines = [f"{sha256(p)}  {rel(p)}" for p in files if p.name != "SHA256SUMS.txt"]
    (ROOT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_zip() -> None:
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in release_files():
            archive.write(path, Path(ROOT.name) / path.relative_to(ROOT))
    digest = sha256(ARCHIVE)
    SIDECAR.write_text(f"{digest}  {ARCHIVE.name}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="write metadata, checksums, and ZIP")
    args = parser.parse_args()
    if not args.build:
        parser.print_help()
        return 0
    files = release_files()
    hits = scan_secrets(files)
    if hits:
        print(json.dumps({"secret_scan_hits": hits}, indent=2), file=sys.stderr)
        return 2
    write_manifest(files)
    files = release_files()
    write_inventory(files)
    files = release_files()
    write_checksums(files)
    build_zip()
    print(json.dumps({"root": str(ROOT), "archive": str(ARCHIVE), "archive_bytes": ARCHIVE.stat().st_size, "archive_sha256": sha256(ARCHIVE), "files": len(release_files())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
