#!/usr/bin/env python3
"""Campaign-local supervisor for pilot completion, freeze, and main launch.

This process only controls the campaign runner in this directory.  It never
changes the schedule or qualification rules; it waits for those artifacts and
uses the runner's existing lock and safety gates.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

RUNTIME = Path(__file__).resolve().parent
RUNNER = RUNTIME / "run_240_campaign.py"
ANALYSIS = RUNTIME / "analysis" / "statistical_analysis.py"
PILOT_SCHEDULE = RUNTIME / "pilot_schedule.csv"
MAIN_SCHEDULE = RUNTIME / "run_schedule.csv"
PILOT_ATTEMPTS = RUNTIME / "pilot_attempts"
MAIN_ATTEMPTS = RUNTIME / "attempts"
PILOT_LOG = RUNTIME / "pilot_runner.log"
MAIN_LOG = RUNTIME / "main_runner.log"
SUPERVISOR_LOG = RUNTIME / "supervisor.log"
PROTOCOL = "CHAOSFLOW-240-OBSERVER-RECOVERY-V1"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    line = f"{utc()} {message}"
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
    print(line, flush=True)


def atomic_json(path: Path, value: object) -> None:
    temp = path.with_name(f".{path.name}.{__import__('os').getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_rows(path: Path, values: list[dict[str, str]]) -> None:
    if not values:
        return
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)
    temp.replace(path)


def attempt_status(attempt_id: str, pilot: bool = True) -> dict:
    base = PILOT_ATTEMPTS if pilot else MAIN_ATTEMPTS
    path = base / attempt_id / "attempt_status.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def pilot_valid(row: dict[str, str]) -> bool:
    if row.get("status") != "PILOT_VALID":
        return False
    ids = [item for item in row.get("attempt_ids", "").split(";") if item]
    if not ids:
        return False
    status = attempt_status(ids[-1])
    if row.get("observer_state") == "OBSERVER_ON":
        observer_ok = status.get("observer_ok")
        if observer_ok is None:
            evidence_path = PILOT_ATTEMPTS / ids[-1] / "observer_evidence.json"
            try:
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                evidence = {}
            observer_ok = evidence.get("observer_started_ok") is True and "evidence" in evidence
        if observer_ok is not True:
            return False
    recovery = status.get("recovery") or {}
    instrumentation_ok = status.get("instrumentation_ok")
    if instrumentation_ok is None:
        instrumentation_ok = row.get("scenario") == "C0" or all(recovery.get(key) is not None for key in ("T0", "T1", "T2", "T3"))
    return (status.get("status") == "PILOT_VALID" and status.get("correctness_ok") is True
            and instrumentation_ok is True)


def pilot_counts() -> tuple[int, int]:
    schedule = rows(PILOT_SCHEDULE)
    return sum(pilot_valid(row) for row in schedule), len(schedule)


def adjudicate_missing_instrumentation() -> None:
    """Preserve and reclassify a legacy pilot decision lacking T0-T3."""
    schedule = rows(PILOT_SCHEDULE)
    changed = False
    adjudication_dir = RUNTIME / "pilot_adjudications"
    invalid_dir = RUNTIME / "invalid_attempts"
    adjudication_dir.mkdir(exist_ok=True)
    invalid_dir.mkdir(exist_ok=True)
    for row in schedule:
        if row.get("status") != "PILOT_VALID":
            continue
        ids = [item for item in row.get("attempt_ids", "").split(";") if item]
        if not ids or pilot_valid(row):
            continue
        attempt_id = ids[-1]
        status = attempt_status(attempt_id)
        recovery = status.get("recovery") or {}
        missing = [key for key in ("T0", "T1", "T2", "T3") if recovery.get(key) is None]
        if row.get("observer_state") == "OBSERVER_ON" and status.get("observer_ok") is not True:
            missing.append("OBSERVER_ON_EVIDENCE")
        record = {"attempt_id": attempt_id, "slot": row, "original_status": row["status"],
                  "adjudicated_status": "PILOT_INVALID",
                  "reason": "legacy pilot decision lacks required recovery/observer instrumentation",
                  "missing_endpoints": missing,
                  "adjudicated_wall_utc": utc(), "original_attempt_status": status}
        atomic_json(adjudication_dir / f"{attempt_id}.json", record)
        source = RUNTIME / "qualifying_runs" / f"{attempt_id}.json"
        if source.exists():
            shutil.copy2(source, invalid_dir / source.name)
        row["status"] = "RETRY_REQUIRED"
        changed = True
        log(f"adjudicated {attempt_id} as PILOT_INVALID: missing required recovery endpoint")
    if changed:
        write_rows(PILOT_SCHEDULE, schedule)


def runner_pids(mode: str) -> list[int]:
    needle = f"run_240_campaign.py --{mode}"
    result = subprocess.run(["pgrep", "-af", needle], capture_output=True, text=True, check=False)
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pid_text, command = line.split(" ", 1)
            pid = int(pid_text)
        except (ValueError, IndexError):
            continue
        if str(RUNNER) in command and pid != __import__('os').getpid():
            pids.append(pid)
    return pids


def launch_runner(mode: str, log_path: Path) -> None:
    log_handle = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(RUNNER), f"--{mode}", "--limit", "240",
                                "--skip-stack", "--retry-limit", "10" if mode == "pilot" else "3"],
                               stdout=log_handle, stderr=subprocess.STDOUT,
                               start_new_session=True, close_fds=True)
    log_handle.close()
    log(f"launched {mode} runner pid={process.pid} log={log_path}")


def read_samples(path: Path) -> list[dict]:
    samples = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (isinstance(item.get("records_in"), int)
                        and isinstance(item.get("lower"), (int, float))
                        and isinstance(item.get("upper"), (int, float))):
                    samples.append(item)
    except FileNotFoundError:
        pass
    return samples


def control_rates(samples: list[dict]) -> list[float]:
    """Estimate cumulative input rates over non-overlapping >=10s windows."""
    rates: list[float] = []
    for index, first in enumerate(samples):
        if first["records_in"] < 100_000 or first["records_in"] >= 1_000_000:
            continue
        for later in samples[index + 1:]:
            span = later["lower"] - first["upper"]
            if span < 10:
                continue
            if later["records_in"] <= first["records_in"] or later["records_in"] > 1_000_000:
                break
            denominator = later["upper"] - first["lower"]
            if denominator > 0:
                rate = (later["records_in"] - first["records_in"]) / denominator
                if math.isfinite(rate) and 100 < rate < 100_000:
                    rates.append(rate)
            break
    return rates


def median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resource_summary(attempt_ids: list[str]) -> dict:
    memory, disk, samples = [], [], 0
    for attempt_id in attempt_ids:
        path = PILOT_ATTEMPTS / attempt_id / "resource_samples.jsonl"
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row.get("available_memory"), (int, float)):
                        memory.append(row["available_memory"])
                    if isinstance(row.get("campaign_disk_free"), (int, float)):
                        disk.append(row["campaign_disk_free"])
                    samples += 1
        except FileNotFoundError:
            continue
    return {"resource_sample_count": samples, "min_available_memory_bytes": min(memory) if memory else None,
            "min_campaign_disk_free_bytes": min(disk) if disk else None,
            "max_available_memory_bytes": max(memory) if memory else None,
            "max_campaign_disk_free_bytes": max(disk) if disk else None}


def freeze_pilot() -> bool:
    schedule = rows(PILOT_SCHEDULE)
    valid_rows = [row for row in schedule if pilot_valid(row)]
    controls = [row for row in valid_rows if row.get("scenario") == "C0"]
    attempt_summaries = []
    all_rates: list[float] = []
    for row in controls:
        attempt_id = row["attempt_ids"].split(";")[-1]
        sample_path = PILOT_ATTEMPTS / attempt_id / "progress_samples.jsonl"
        rates = control_rates(read_samples(sample_path))
        if rates:
            all_rates.extend(rates)
            attempt_summaries.append({"slot": row["slot"], "attempt_id": attempt_id,
                                      "observer_state": row["observer_state"], "rates": rates,
                                      "attempt_median_rate": median(rates),
                                      "samples_path": str(sample_path)})
    if len(valid_rows) != 16 or len(controls) != 2 or not all_rates:
        log(f"pilot not freezeable: valid={len(valid_rows)} controls={len(controls)} rates={len(all_rates)}")
        return False
    baseline = median(all_rates)
    baseline_doc = {
        "protocol": PROTOCOL,
        "baseline_rate": baseline,
        "unit": "input records per second",
        "method": "median of >=10 second cumulative records_in slopes from both valid C0 pilot controls; windows start after 100,000 records",
        "pilot_valid_runs": len(valid_rows),
        "control_attempts": attempt_summaries,
        "all_window_rates": all_rates,
        "computed_wall_utc": utc(),
        "resource_summary": resource_summary([row["attempt_ids"].split(";")[-1] for row in valid_rows]),
    }
    atomic_json(RUNTIME / "pilot_baseline.json", baseline_doc)
    invalid = []
    for path in sorted((RUNTIME / "invalid_attempts").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if value.get("mode") == "pilot":
            invalid.append({"attempt_id": value.get("attempt_id"), "scenario": value.get("scenario"),
                            "status": value.get("status"), "reason": value.get("reason"),
                            "directory": value.get("directory")})
    pilot_report = [
        "# ChaosFlow 240 Campaign — Pilot Report", "", f"- Protocol: `{PROTOCOL}`",
        f"- Completed valid pilot cells: **{len(valid_rows)}/16**",
        f"- Strict correctness gate: exact oracle and validator pass; no qualification weakening",
        f"- Frozen C0 baseline: **{baseline:.3f} input records/s**",
        "- Baseline method: median of independent cumulative `records_in` slopes over at least 10 seconds, using both valid C0 controls.",
        "", "## Pilot coverage", "", "| Slot | Scenario | Observer | Status | Attempts |", "|---:|---|---|---|---:|",
    ]
    for row in schedule:
        pilot_report.append(f"| {row['slot']} | {row['scenario']} | {row['observer_state']} | {row['status']} | {len([x for x in row.get('attempt_ids','').split(';') if x])} |")
    pilot_report += ["", "## Preserved invalid attempts", "", f"Count: {len(invalid)}", ""]
    for item in invalid:
        pilot_report.append(f"- `{item['attempt_id']}`: {item['scenario']} — {item.get('reason') or item['status']}")
    (RUNTIME / "pilot_report.md").write_text("\n".join(pilot_report) + "\n", encoding="utf-8")

    def normal_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    power_rows = []
    n = 15
    zcrit = 1.959963984540054
    for effect in (0.5, 0.8, 1.0):
        noncentral = effect * math.sqrt(n / 2)
        power = (1 - normal_cdf(zcrit - noncentral)) + normal_cdf(-zcrit - noncentral)
        power_rows.append((effect, power))
    power_doc = [
        "# ChaosFlow 240 Campaign — Design-Based Power Note", "",
        "The approved design has 15 sequential observations per scenario × observer cell. The table below is a planning calculation, not a claim about observed effects.",
        "It uses a two-sided normal approximation for an independent ON/OFF contrast with equal n=15 per cell, alpha=0.05, and standardized effect size d.", "",
        "| Assumed standardized effect | Approximate power |", "|---:|---:|",
    ]
    power_doc += [f"| {effect:.1f} | {power:.3f} |" for effect, power in power_rows]
    power_doc += ["", "Observed confidence intervals and multiplicity-adjusted results will be computed only after all 240 qualifying observations are present."]
    (RUNTIME / "power_analysis.md").write_text("\n".join(power_doc) + "\n", encoding="utf-8")

    manifest = {
        "campaign": "ChaosFlow Research Campaign",
        "protocol": PROTOCOL,
        "status": "FROZEN_BEFORE_MAIN_CAMPAIGN",
        "matrix": {"scenarios": [f"C{i}" for i in range(8)], "observer_states": ["OBSERVER_ON", "OBSERVER_OFF"],
                   "repetitions_per_cell": 15, "qualifying_observations": 240},
        "pilot": {"schedule": str(PILOT_SCHEDULE), "report": str(RUNTIME / "pilot_report.md"),
                  "baseline": baseline_doc, "valid_cells": len(valid_rows), "invalid_attempts": len(invalid)},
        "main_schedule": str(MAIN_SCHEDULE), "runner": str(RUNNER),
        "source_snapshot": str(RUNTIME / "source_snapshot"),
        "code_fingerprints": {name: sha256(RUNTIME / name) for name in
                              ("run_240_campaign.py", "campaign_supervisor.py", "campaign_dashboard.py")},
        "frozen_wall_utc": utc(),
    }
    atomic_json(RUNTIME / "campaign_manifest.json", manifest)
    marker = (RUNTIME / "frozen_protocol.md").read_text(encoding="utf-8")
    if "FROZEN BEFORE MAIN CAMPAIGN" not in marker:
        with (RUNTIME / "frozen_protocol.md").open("a", encoding="utf-8") as stream:
            stream.write(f"\n\n## Pilot repair continuation and final freeze ({utc()})\n\n"
                         f"All 16 pilot cells are strict-valid after the campaign-scoped HDFS transport, Spark readiness, "
                         f"checkpoint lookup, and observer launch repairs. "
                         f"The approved matrix and qualification criteria are unchanged. The frozen C0 baseline is "
                         f"{baseline:.3f} input records/s, computed from both valid C0 controls using independent cumulative `records_in` slopes.\n\n"
                         "Status: **FROZEN BEFORE MAIN CAMPAIGN**.\n")
    status_updates = {
        "README.md": ("## Repair continuation and pilot completion\n\n"
                       f"The transient HDFS WebHDFS readability failure was reproduced and diagnosed as transport-level; "
                       f"a bounded retry plus diagnostic capture was verified without weakening the exact oracle. The C3 "
                       f"Spark readiness probe was also repaired to query the campaign Spark master JSON endpoint. The pilot "
                       f"now has 16/16 strict-valid cells, the C0 baseline is {baseline:.3f} input records/s, and the main "
                       "schedule is frozen.\n"),
        "PILOT_BLOCKED_REPORT.md": ("\n\n## Resolution and continuation\n\n"
                                    f"The block was resolved after a controlled diagnostic reproduced a strict oracle/validator pass "
                                    f"with healthy HDFS blocks and matching full-row multiset hashes. The repair is bounded retry "
                                    f"only for transport-level UNKNOWN reads and retains HDFS diagnostics. A separate Spark readiness "
                                    f"probe defect was repaired and the affected C3 pilot attempt was adjudicated invalid and replaced. "
                                    f"The pilot is now strict-valid at 16/16; baseline={baseline:.3f} input records/s.\n"),
        "campaign_preflight_report.md": ("\n\n## Repair continuation and final preflight disposition\n\n"
                                          f"The original C5 block is resolved by the documented campaign-scoped transport-read repair. "
                                          f"The exact matrix, fault treatments, observer states, and qualification criteria are unchanged. "
                                          f"The Spark worker readiness probe was corrected to use the published campaign Spark master JSON "
                                          f"endpoint; the pre-repair C3 pilot decision lacking T2/T3 was preserved and replaced. "
                                          f"All 16 pilot cells are strict-valid and the frozen C0 baseline is {baseline:.3f} input records/s. "
                                          "The main campaign may proceed under the frozen protocol.\n"),
    }
    for name, text in status_updates.items():
        path = RUNTIME / name
        existing = path.read_text(encoding="utf-8")
        if "Repair continuation and pilot completion" not in existing and "Resolution and continuation" not in existing and "Repair continuation and final preflight disposition" not in existing:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(text)
    log(f"pilot frozen: baseline_rate={baseline:.3f} valid=16/16")
    return True


def main() -> int:
    log("supervisor started")
    restart_count = 0
    while True:
        adjudicate_missing_instrumentation()
        valid, total = pilot_counts()
        if valid == total == 16:
            break
        pids = runner_pids("pilot")
        if not pids:
            restart_count += 1
            if restart_count > 3:
                log(f"pilot blocked after {restart_count - 1} runner restarts: valid={valid}/{total}")
                (RUNTIME / "SUPERVISOR_BLOCKED.md").write_text(
                    f"# Campaign supervisor blocked\n\nPilot remains at {valid}/{total} valid cells after bounded runner restarts.\n",
                    encoding="utf-8")
                return 2
            launch_runner("pilot", PILOT_LOG)
        else:
            log(f"pilot active pid(s)={pids}; valid={valid}/{total}")
        time.sleep(30)
    if not freeze_pilot():
        log("pilot complete but baseline freeze failed")
        return 2
    main_valid = sum(1 for row in rows(MAIN_SCHEDULE) if row.get("status") == "QUALIFYING")
    if main_valid < 240 and not runner_pids("main"):
        launch_runner("main", MAIN_LOG)
    log(f"main runner ensured: existing qualifying={main_valid}/240")
    while True:
        schedule = rows(MAIN_SCHEDULE)
        qualifying = sum(row.get("status") == "QUALIFYING" for row in schedule)
        pids = runner_pids("main")
        log(f"main monitor: qualifying={qualifying}/240 active={pids}")
        if qualifying == 240:
            log("main schedule reached 240 qualifying rows")
            result = subprocess.run([sys.executable, str(ANALYSIS)], cwd=RUNTIME,
                                    capture_output=True, text=True, check=False)
            if result.returncode != 0:
                log(f"final analysis failed: {result.stderr[-2000:]}")
                return 2
            log(f"final analysis completed: {result.stdout.strip()}")
            return 0
        if not pids:
            launch_runner("main", MAIN_LOG)
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
