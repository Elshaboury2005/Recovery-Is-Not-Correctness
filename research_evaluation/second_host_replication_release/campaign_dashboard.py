#!/usr/bin/env python3
"""Durable campaign dashboard; writes actual ledger snapshots every 15 seconds."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time

RUNTIME = Path(__file__).resolve().parent
OUT = RUNTIME / "dashboard.log"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(name: str) -> dict:
    try:
        return json.loads((RUNTIME / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def schedule_counts(name: str) -> dict[str, int]:
    try:
        with (RUNTIME / name).open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    except FileNotFoundError:
        return {}
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.get("status", "UNKNOWN")] = counts.get(row.get("status", "UNKNOWN"), 0) + 1
    return counts


def main() -> int:
    while True:
        progress = read_json("progress.json")
        main_counts = schedule_counts("run_schedule.csv")
        pilot_counts = schedule_counts("pilot_schedule.csv")
        current = progress.get("current") or {}
        qualifying = main_counts.get("QUALIFYING", 0)
        invalid = progress.get("invalid_attempts", 0)
        line = (f"{utc()} | MAIN {qualifying:03d}/240 | PILOT {pilot_counts.get('PILOT_VALID', 0):02d}/16 | "
                f"attempts={progress.get('attempt_count', 0)} invalid={invalid} | "
                f"phase={progress.get('phase', 'UNKNOWN')} | "
                f"current={current.get('slot', '-')}:{current.get('scenario', '-')}:{current.get('observer_state', '-')} | "
                f"event={progress.get('last_event', '')}")
        with OUT.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        print(line, flush=True)
        time.sleep(15)


if __name__ == "__main__":
    raise SystemExit(main())
