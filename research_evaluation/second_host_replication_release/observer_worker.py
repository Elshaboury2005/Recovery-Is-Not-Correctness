#!/usr/bin/env python3
"""Run the repository recovery observer for one campaign attempt.

The campaign runner keeps the minimal same-clock collector outside this
process. This process is the experimental observer whose ON/OFF effect is
being measured.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

from app.reliability.docker_controller import DockerController
from app.reliability.recovery_observer import RecoveryObserver
from app.reliability.safety import SafetyValidator


def get_json(path: str, token: str):
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/" + path,
        headers={"Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-service", required=True)
    parser.add_argument("--label", default="observer-on")
    parser.add_argument("--baseline-rate", type=float, default=None)
    args = parser.parse_args()
    token = os.environ["CHAOSFLOW_TOKEN"]
    docker = DockerController(SafetyValidator())
    observer = None

    def pipeline_probe():
        progress = get_json(f"pipeline-runs/{args.run_id}/progress", token)
        spark = progress.get("spark") or {}
        return {
            "counter": {
                "value": spark.get("recordsIn"),
                "stage": "streaming_completed_batch_input_rows",
                "epoch": args.run_id,
                "source": "pipeline progress API",
            },
            "clock_id": observer.timeline.clock_id,
        }

    observer = RecoveryObserver(
        {
            "infrastructure": lambda: docker.observe_container(args.target_service),
            "service": lambda: docker.observe_service(args.target_service),
        },
        pipeline_probe=pipeline_probe,
        interval=0.5,
        baseline_rate=args.baseline_rate,
        baseline_stage="streaming_completed_batch_input_rows",
    )
    start = time.monotonic()
    started_ok = observer.start()
    terminal = None
    while time.monotonic() - start < 960:
        try:
            terminal = get_json(f"pipeline-runs/{args.run_id}", token)
            if terminal.get("status") not in ("pending", "running"):
                break
        except Exception:
            pass
        time.sleep(0.5)
    evidence = observer.stop()
    print(json.dumps({
        "observer_label": args.label,
        "observer_started_ok": started_ok,
        "run_id": args.run_id,
        "target_service": args.target_service,
        "terminal": terminal,
        "evidence": evidence,
        "observer_wall_seconds": time.monotonic() - start,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
