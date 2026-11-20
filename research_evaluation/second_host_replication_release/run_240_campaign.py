#!/usr/bin/env python3
"""Sequential, resumable ChaosFlow 240-run campaign runner."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

RUNTIME = Path(__file__).resolve().parent
ROOT = RUNTIME
COMPOSE = RUNTIME / "compose.chaosflow-240.yml"
PROJECT = "chaosflow-240-replication"
API_BASE = "http://127.0.0.1:38000"
DATASET = ROOT / "dataset/sales_large.csv"
DATASET_SHA256 = "bff70d62204d7d53eda5f3d4a9696b9d39be7f43c0f104e09a4f3b30a122c867"
EXPECTED_INPUT = 1_000_000
EXPECTED_OUTPUT = 966_002
PLAN_SEED = 2_026_11_20
PILOT_SEED = PLAN_SEED + 1
MIN_AVAILABLE_MEMORY = 1 * 1024**3
MIN_CAMPAIGN_DISK = 5 * 1024**3
ACTIVE_RECORD_FLOOR = 100_000
RUN_TIMEOUT = 960
FAULT_GATE_TIMEOUT = 480
TERMINAL = {"succeeded", "failed", "cancelled"}

CONTAINERS = {service: f"{PROJECT}-{service}-1" for service in
              ("kafka", "spark-worker", "spark-master", "datanode", "namenode", "backend", "postgres")}

SCENARIOS = {
    "C0": {"name": "No Fault", "target": "kafka", "fault": None, "duration": 0},
    "C1": {"name": "Kafka Container Stop", "target": "kafka", "fault": "container_stop", "duration": 5},
    "C2": {"name": "Kafka Container Restart", "target": "kafka", "fault": "container_restart", "duration": 5},
    "C3": {"name": "Spark Worker Failure", "target": "spark-worker", "fault": "container_stop", "duration": 5},
    "C4": {"name": "HDFS DataNode Failure", "target": "datanode", "fault": "container_stop", "duration": 5},
    "C5": {"name": "Network Fault", "target": "datanode", "fault": "network_disruption", "duration": 5},
    "C6": {"name": "Storage Fault", "target": "datanode", "fault": "storage_pressure", "duration": 5},
    "C7": {"name": "Checkpoint-Related Recovery", "target": "datanode", "fault": "checkpoint_quarantine", "duration": 1},
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, value=None, *, text: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if text is None:
        text = json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def cmd(args: list[str], timeout: float = 30, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          input=input_text, check=False)


def dotenv(path: Path) -> dict[str, str]:
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def inspect_container(name: str) -> dict:
    result = cmd(["docker", "inspect", name], timeout=15)
    if result.returncode != 0:
        return {"name": name, "error": result.stderr.strip(), "running": False}
    raw = json.loads(result.stdout)[0]
    state = raw.get("State") or {}
    return {"name": raw.get("Name"), "id": raw.get("Id"), "status": state.get("Status"),
            "running": state.get("Running"), "health": (state.get("Health") or {}).get("Status"),
            "started_at": state.get("StartedAt"), "restart_count": state.get("RestartCount", 0),
            "exit_code": state.get("ExitCode"), "oom_killed": state.get("OOMKilled"),
            "project": (raw.get("Config") or {}).get("Labels", {}).get("com.docker.compose.project"),
            "service": (raw.get("Config") or {}).get("Labels", {}).get("com.docker.compose.service")}


def compose(*args: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return cmd(["docker", "compose", "--project-name", PROJECT, "--env-file", str(ROOT / ".env"),
                "-f", str(COMPOSE), *args], timeout=timeout)


def project_healthy() -> tuple[bool, dict]:
    states = {service: inspect_container(name) for service, name in CONTAINERS.items()}
    ok = True
    for service, state in states.items():
        if not state.get("running"):
            ok = False
        if service in {"postgres", "kafka", "spark-master", "namenode", "datanode"} and state.get("health") != "healthy":
            ok = False
    return ok, states


def ensure_stack(timeout: float = 240) -> None:
    result = compose("up", "-d", timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"campaign compose up failed: {result.stderr[-2000:]}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ok, _ = project_healthy()
        if ok:
            return
        time.sleep(5)
    raise RuntimeError("campaign Compose project did not reach the required healthy state")


class Api:
    def __init__(self, username: str, password: str):
        self.username, self.password, self.token = username, password, ""
        self.login()

    def login(self) -> None:
        body = urllib.parse.urlencode({"username": self.username, "password": self.password}).encode()
        request = urllib.request.Request(API_BASE + "/api/auth/login", data=body, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(request, timeout=20) as response:
            self.token = json.load(response)["access_token"]

    def request(self, method: str, path: str, body=None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + self.token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(API_BASE + "/api/" + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                self.login()
                return self.request(method, path, body, timeout)
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"API {method} {path} HTTP {exc.code}: {detail[-1000:]}") from exc


def pipeline_config(run_id: str) -> dict:
    return {"pipeline": {"name": run_id, "version": "1.0"},
            "source": {"type": "csv", "path": "/app/sample-data/sales_large.csv"},
            "schema": [{"name": "transaction_id", "type": "string"}, {"name": "customer_id", "type": "string"},
                       {"name": "product_id", "type": "string"}, {"name": "amount", "type": "double"},
                       {"name": "timestamp", "type": "string"}],
            "processing": {"operations": [{"type": "remove_nulls"}, {"type": "filter", "condition": "amount > 0"}]},
            "streaming": {"enabled": True, "trigger_interval_seconds": 2, "idle_timeout_seconds": 10,
                          "max_runtime_seconds": 840, "starting_offsets": "earliest", "max_offsets_per_trigger": 50000},
            "messaging": {"broker": "kafka", "topic": run_id, "partitions": 3, "replication_factor": 1},
            "processing_engine": {"type": "spark"},
            "storage": {"type": "hdfs", "path": f"/data/chaosflow-240-replication/{run_id}"},
            "monitoring": {"enabled": True}}


def experiment_yaml(run_id: str, scenario: dict) -> str:
    return (f"experiment:\n  name: {run_id}\n" f"target:\n  service: {scenario['target']}\n"
            f"fault:\n  type: {scenario['fault']}\n  duration: {scenario['duration']}\n"
            "validation:\n  expected_data_loss: 0\n  max_recovery_time: 180\nobserver_enabled: false\n")


def make_schedule(path: Path, *, pilot: bool) -> list[dict]:
    if path.exists():
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        expected = 16 if pilot else 240
        if len(rows) != expected:
            raise RuntimeError(f"frozen schedule has {len(rows)} rows, expected {expected}")
        return rows
    rng = random.Random(PILOT_SEED if pilot else PLAN_SEED)
    cells = [(scenario, observer) for scenario in SCENARIOS for observer in ("OBSERVER_ON", "OBSERVER_OFF")]
    rows = []
    if pilot:
        rng.shuffle(cells)
        for slot, (scenario, observer) in enumerate(cells, 1):
            rows.append({"slot": str(slot), "block": "P01", "repetition": "1", "order": str(slot),
                         "scenario": scenario, "observer_state": observer, "status": "PLANNED", "attempt_ids": ""})
    else:
        for block in range(1, 16):
            block_cells = list(cells)
            rng.shuffle(block_cells)
            for order, (scenario, observer) in enumerate(block_cells, 1):
                slot = (block - 1) * len(cells) + order
                rows.append({"slot": str(slot), "block": f"B{block:02d}", "repetition": str(block), "order": str(order),
                             "scenario": scenario, "observer_state": observer, "status": "PLANNED", "attempt_ids": ""})
    fields = list(rows[0])
    text = ",".join(fields) + "\n" + "".join(",".join(row.get(k, "") for k in fields) + "\n" for row in rows)
    atomic_write(path, text=text)
    return rows


def update_schedule(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0])
    text = ",".join(fields) + "\n" + "".join(",".join(row.get(k, "") for k in fields) + "\n" for row in rows)
    atomic_write(path, text=text)


def available_memory() -> int:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    return values.get("MemAvailable", 0)


def resource_sample() -> dict:
    disk = shutil.disk_usage(RUNTIME)
    ok, states = project_healthy()
    return {"wall_utc": utc(), "available_memory": available_memory(), "campaign_disk_free": disk.free,
            "project_healthy": ok, "containers": states}


def hdfs_path_exists(path: str) -> bool:
    raw = path.replace("hdfs://namenode:9000", "")
    result = cmd(["docker", "exec", CONTAINERS["namenode"], "hdfs", "dfs", "-test", "-e", raw], timeout=20)
    return result.returncode == 0


def hdfs_cmd(args: list[str], timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return cmd(["docker", "exec", CONTAINERS["namenode"], "hdfs", "dfs", *args], timeout=timeout)


def functional_probe(target: str) -> dict:
    if target == "kafka":
        result = cmd(["docker", "exec", CONTAINERS["kafka"], "kafka-broker-api-versions", "--bootstrap-server", "kafka:9092"], timeout=15)
        return {"target": target, "ok": result.returncode == 0, "returncode": result.returncode,
                "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}
    if target == "spark-worker":
        # The Spark master image is intentionally minimal and does not ship
        # curl.  Query the campaign-owned, published master UI from the host;
        # the JSON endpoint is the same worker-membership source, with the
        # redirect followed explicitly.
        result = cmd(["curl", "-sfL", "http://127.0.0.1:38080/json/"], timeout=15)
        try:
            payload = json.loads(result.stdout)
            workers = [w for w in payload.get("workers", []) if w.get("state") == "ALIVE"]
            ok = result.returncode == 0 and bool(workers)
        except json.JSONDecodeError:
            workers, ok = [], False
        return {"target": target, "ok": ok, "returncode": result.returncode, "alive_workers": workers,
                "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}
    if target == "datanode":
        result = cmd(["docker", "exec", CONTAINERS["datanode"], "curl", "-sf", "http://localhost:9864/"], timeout=15)
        return {"target": target, "ok": result.returncode == 0, "returncode": result.returncode,
                "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}
    return {"target": target, "ok": False, "reason": "no probe"}


def checkpoint_metadata(checkpoint_path: str) -> str | None:
    raw = checkpoint_path.replace("hdfs://namenode:9000", "")
    # Hadoop's bundled `hdfs dfs -find` does not accept the GNU-like
    # `-type f` expression used by the original campaign runner.  Use the
    # supported bounded recursive listing and retain only regular-file rows.
    result = hdfs_cmd(["-ls", "-R", raw], timeout=30)
    if result.returncode != 0:
        return None
    paths = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].startswith("-"):
            paths.append(fields[-1])
    offsets = [line for line in paths if "/offsets/" in line]
    return (offsets or paths)[0] if (offsets or paths) else None


def qdisc_active() -> bool:
    result = cmd(["docker", "exec", CONTAINERS["datanode"], "tc", "qdisc", "show", "dev", "eth0"], timeout=15)
    return result.returncode == 0 and ("netem" in result.stdout or "loss" in result.stdout)


def parse_last_json(text: str) -> dict:
    try:
        return json.loads(text.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {}


def compact_validation_report(report: dict) -> dict:
    keys = ("status", "output_correct", "validation_status", "validation_passed", "reason",
            "error", "actual_records", "expected_records", "missing_records", "unexpected_records")
    return {key: report.get(key) for key in keys if key in report}


def transient_read_failure(result: dict) -> bool:
    """Recognize transport/readability UNKNOWNs without retrying correctness failures."""
    report = result.get("report") or {}
    text = json.dumps({"report": report, "stdout": result.get("stdout", ""),
                       "stderr": result.get("stderr", "")}, sort_keys=True).lower()
    markers = ("incompleteread", "connection broken", "connection reset", "remote end closed",
               "chunkedencodingerror", "protocolerror", "readtimeout", "remotedisconnected")
    return result.get("exit_code") != 0 and report.get("output_correct") is None and any(marker in text for marker in markers)


def capture_hdfs_diagnostics(output_path: str, run_dir: Path) -> None:
    """Retain bounded NameNode evidence whenever post-run reads need diagnosis."""
    raw = output_path.replace("hdfs://namenode:9000", "")
    evidence = {}
    for name, args in (
        ("listing", ["-ls", "-R", raw]),
        ("content_summary", ["-du", "-h", raw]),
    ):
        try:
            result = hdfs_cmd(args, timeout=120)
            evidence[name] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        except Exception as exc:
            evidence[name] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        fsck = cmd(["docker", "exec", CONTAINERS["namenode"], "hdfs", "fsck", raw,
                    "-files", "-blocks", "-locations"], timeout=120)
        evidence["fsck"] = {"returncode": fsck.returncode, "stdout": fsck.stdout, "stderr": fsck.stderr}
    except Exception as exc:
        evidence["fsck"] = {"error": f"{type(exc).__name__}: {exc}"}
    atomic_write(run_dir / "hdfs_diagnostics.json", evidence)


def run_oracle(config: dict, output_path: str) -> tuple[dict, dict]:
    validator_code = ("import json,sys\nfrom app.reliability.data_consistency_validator import DataConsistencyValidator\n"
                      "cfg=json.loads(sys.argv[1])\n"
                      "r=DataConsistencyValidator().validate(output_location={'storage_type':'hdfs','path':sys.argv[2]},"
                      "pipeline_config=cfg,writer_stopped=True,expected_source_sha256=sys.argv[3])\n"
                      "print(json.dumps(r,sort_keys=True))\n"
                      "raise SystemExit(0 if r.get('validation_status')=='PASS' else 1)\n")
    oracle_result = validation_result = None
    attempts = []
    for attempt_number in range(1, 4):
        oracle = cmd(["docker", "exec", CONTAINERS["backend"], "python", "/app/tests/sales_output_oracle.py",
                      "--source", "/app/sample-data/sales_large.csv", "--output-path", output_path], timeout=600)
        oracle_result = {"exit_code": oracle.returncode, "stdout": oracle.stdout, "stderr": oracle.stderr,
                         "report": parse_last_json(oracle.stdout)}
        validation = cmd(["docker", "exec", CONTAINERS["backend"], "python", "-c", validator_code,
                          json.dumps(config), output_path, DATASET_SHA256], timeout=360)
        validation_result = {"exit_code": validation.returncode, "stdout": validation.stdout,
                             "stderr": validation.stderr, "report": parse_last_json(validation.stdout)}
        attempts.append({"attempt": attempt_number,
                         "oracle": {"exit_code": oracle_result["exit_code"],
                                    "report": compact_validation_report(oracle_result["report"]),
                                    "stderr": oracle_result["stderr"][-2000:]},
                         "validator": {"exit_code": validation_result["exit_code"],
                                       "report": compact_validation_report(validation_result["report"]),
                                       "stderr": validation_result["stderr"][-2000:]}})
        both_correct = (oracle_result["exit_code"] == 0
                        and oracle_result["report"].get("output_correct") is True
                        and validation_result["exit_code"] == 0
                        and validation_result["report"].get("output_correct") is True
                        and validation_result["report"].get("validation_passed") is True)
        if both_correct:
            break
        if attempt_number >= 3 or not (transient_read_failure(oracle_result) or transient_read_failure(validation_result)):
            break
        time.sleep(5 * (2 ** (attempt_number - 1)))
    assert oracle_result is not None and validation_result is not None
    oracle_result["retry_attempts"] = attempts
    validation_result["retry_attempts"] = attempts
    return oracle_result, validation_result


def launch_event_capture(path: Path):
    process = subprocess.Popen(["docker", "events", "--format", "{{json .}}",
                                "--filter", f"label=com.docker.compose.project={PROJECT}"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stop = threading.Event()

    def loop():
        with path.open("x", encoding="utf-8") as stream:
            while not stop.is_set() and process.stdout is not None:
                line = process.stdout.readline()
                if not line:
                    break
                stream.write(json.dumps({"received_monotonic": time.monotonic(), "received_wall_utc": utc(),
                                         "raw": line.strip()}) + "\n")
                stream.flush()

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return process, stop, thread


def active_gate(progress: dict) -> bool:
    stages = {row.get("key"): row.get("state") for row in progress.get("stages") or []}
    spark = progress.get("spark") or {}
    source = progress.get("source") or {}
    records, total = spark.get("recordsIn"), source.get("rowsTotal")
    return stages.get("spark") == "active" and isinstance(records, int) and isinstance(total, int) and ACTIVE_RECORD_FLOOR <= records < total


def fault_active_for(code: str, before: dict, current: dict, context: dict) -> bool:
    if code in {"C1", "C3", "C4"}:
        return current.get("container", {}).get("running") is False
    if code == "C2":
        return (current.get("container", {}).get("started_at") != before.get("started_at")
                or current.get("container", {}).get("restart_count", 0) > before.get("restart_count", 0))
    if code == "C5":
        return current.get("qdisc_active") is True
    if code == "C6":
        return context.get("storage_file_exists") is True
    if code == "C7":
        return context.get("checkpoint_quarantined") is True
    return False


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def start_observer(api: Api, pipeline_id: str, target: str, state: str, baseline_rate: float | None):
    if state != "OBSERVER_ON":
        return None
    return subprocess.Popen([
        "docker", "exec", "-e", "CHAOSFLOW_TOKEN=" + api.token, "-e", "PYTHONPATH=/app",
        CONTAINERS["backend"], "python",
        "/campaign/observer_worker.py", "--run-id", pipeline_id, "--target-service", target,
        "--label", "observer-on", "--baseline-rate", str(baseline_rate or 0),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def stop_observer(process, run_dir: Path) -> dict:
    if process is None:
        evidence = {"observer_disabled": True}
        atomic_write(run_dir / "observer_evidence.json", evidence)
        return evidence
    try:
        # The observer exits by itself after seeing the terminal pipeline
        # state.  Give it time to flush its complete JSON evidence; signaling
        # the docker-exec wrapper immediately can truncate the pipe.
        stdout, stderr = process.communicate(timeout=25)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
    (run_dir / "observer_stdout.log").write_text(stdout or "", encoding="utf-8")
    (run_dir / "observer_stderr.log").write_text(stderr or "", encoding="utf-8")
    try:
        evidence = json.loads((stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        evidence = {"parse_error": str(exc), "stdout": stdout}
    atomic_write(run_dir / "observer_evidence.json", evidence)
    return evidence


def throughput_endpoint(samples: list[dict], t2: dict | None, baseline_rate: float | None) -> dict:
    if not t2 or not baseline_rate or baseline_rate <= 0:
        return {"status": "unobservable", "reason": "missing T2 or frozen baseline", "event": None}
    after = t2["upper"]
    clean = []
    for sample in samples:
        value, lower, upper = sample.get("records_in"), sample.get("lower"), sample.get("upper")
        if not isinstance(value, int) or not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
            clean = []
            continue
        if upper < after:
            continue
        if clean and (lower < clean[-1]["upper"] or value < clean[-1]["value"] or upper - clean[-1]["lower"] > 3):
            clean = []
        clean.append({"lower": lower, "upper": upper, "value": value})
        if len(clean) >= 2 and clean[-1]["lower"] - clean[0]["upper"] >= 10:
            first, last = clean[0], clean[-1]
            rate = (last["value"] - first["value"]) / max(last["upper"] - first["lower"], 1e-9)
            if rate < 0.9 * baseline_rate:
                clean = [last]
            elif clean[-1]["lower"] - clean[0]["upper"] >= 30:
                return {"status": "observed", "event": {"lower": clean[0]["lower"], "upper": clean[0]["upper"],
                        "confirmed_at": last["upper"], "rate_lower": rate, "baseline_rate": baseline_rate}}
    return {"status": "right_censored" if clean else "unobservable", "reason": "no complete sustained window", "event": None}


def cleanup_run(output_path: str, checkpoint_path: str, topic: str, run_dir: Path, context: dict) -> dict:
    actions = []
    if context.get("checkpoint_quarantined") and context.get("checkpoint_quarantine"):
        checkpoint_file = context["checkpoint_file"]
        quarantine = context["checkpoint_quarantine"]
        target_exists = hdfs_path_exists(checkpoint_file)
        quarantine_exists = hdfs_path_exists(quarantine)
        if target_exists:
            # Spark may commit a replacement offset file during the brief
            # quarantine. Preserve that active file; remove only the
            # run-scoped quarantine copy instead of overwriting live state.
            removed = hdfs_cmd(["-rm", "-f", quarantine.replace("hdfs://namenode:9000", "")], timeout=30) if quarantine_exists else None
            restore_returncode = 0 if removed is None else removed.returncode
            actions.append({"action": "restore_checkpoint_before_cleanup", "returncode": restore_returncode,
                            "mode": "target_already_present_preserved",
                            "target_exists": target_exists, "quarantine_exists": quarantine_exists,
                            "stdout": "" if removed is None else removed.stdout[-500:],
                            "stderr": "" if removed is None else removed.stderr[-500:]})
        else:
            restored = hdfs_cmd(["-mv", quarantine, checkpoint_file], timeout=30)
            actions.append({"action": "restore_checkpoint_before_cleanup", "returncode": restored.returncode,
                            "mode": "rename_quarantine_back", "target_exists": target_exists,
                            "quarantine_exists": quarantine_exists,
                            "stdout": restored.stdout[-500:], "stderr": restored.stderr[-500:]})
    for path in (output_path, checkpoint_path):
        result = hdfs_cmd(["-rm", "-r", "-f", path.replace("hdfs://namenode:9000", "")], timeout=60)
        actions.append({"action": "remove_hdfs_path", "path": path, "returncode": result.returncode,
                        "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]})
    result = cmd(["docker", "exec", CONTAINERS["kafka"], "kafka-topics", "--delete", "--topic", topic,
                  "--bootstrap-server", "kafka:9092"], timeout=30)
    actions.append({"action": "delete_kafka_topic", "topic": topic, "returncode": result.returncode,
                    "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]})
    if context.get("storage_file"):
        result = cmd(["docker", "exec", CONTAINERS["datanode"], "rm", "-f", context["storage_file"]], timeout=30)
        actions.append({"action": "remove_storage_scratch", "path": context["storage_file"], "returncode": result.returncode,
                        "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]})
    atomic_write(run_dir / "cleanup.json", {"completed_wall_utc": utc(), "actions": actions})
    return {"actions": actions, "completed": all(a.get("returncode") == 0 for a in actions)}


def run_attempt(api: Api, slot: dict, run_dir: Path, *, mode: str, baseline_rate: float | None) -> dict:
    run_id = run_dir.name
    code, scenario = slot["scenario"], SCENARIOS[slot["scenario"]]
    config = pipeline_config(run_id)
    output_path = config["storage"]["path"]
    checkpoint_path = f"hdfs://namenode:9000/checkpoints/streaming-UNKNOWN"
    manifest = {"attempt_id": run_id, "mode": mode, "slot": slot, "scenario": code, "scenario_name": scenario["name"],
                "observer_state": slot["observer_state"], "created_wall_utc": utc(),
                "protocol": "CHAOSFLOW-240-OBSERVER-RECOVERY-V1", "project": PROJECT,
                "dataset": {"path": str(DATASET), "sha256": DATASET_SHA256, "input_rows": EXPECTED_INPUT,
                            "expected_output_rows": EXPECTED_OUTPUT}, "config": config, "status": "RUNNING"}
    atomic_write(run_dir / "run_manifest.json", manifest)
    atomic_write(run_dir / "config_snapshot.json", config)
    for name in ("progress_samples.jsonl", "readiness_samples.jsonl", "resource_samples.jsonl", "fault_events.jsonl"):
        (run_dir / name).touch()

    event_process, event_stop, event_thread = launch_event_capture(run_dir / "docker_events.jsonl")
    observer = None
    collector_stop = threading.Event()
    collector_thread = None
    samples, endpoint = [], {"t0": None, "t1": None, "t2": None, "t3": None, "t5": None}
    context = {"manual_fault_active": False, "storage_file_exists": False, "checkpoint_quarantined": False}
    before_target = inspect_container(CONTAINERS[scenario["target"]])
    fault_dispatch = None
    direct_action = {"actions": [], "restoration": None}
    pipeline_id = None

    try:
        lower = time.monotonic()
        launched = api.request("POST", "pipelines/run", {"yaml_content": json.dumps(config)}, timeout=30)
        upper = time.monotonic()
        pipeline_id = launched.get("pipeline_run_id")
        atomic_write(run_dir / "launch.json", {"response": launched, "lower": lower, "upper": upper, "wall_utc": utc()})
        if not pipeline_id:
            raise RuntimeError(f"pipeline launch returned no pipeline_run_id: {launched}")
        checkpoint_path = f"hdfs://namenode:9000/checkpoints/streaming-{pipeline_id}"
        atomic_write(run_dir / "run_manifest.json", {**manifest, "pipeline_id": pipeline_id, "checkpoint_path": checkpoint_path})
        observer = start_observer(api, pipeline_id, scenario["target"], slot["observer_state"], baseline_rate)
        latest = {"progress": {}}

        def collect() -> None:
            while not collector_stop.is_set():
                sample_lower = time.monotonic()
                try:
                    progress = api.request("GET", f"pipeline-runs/{pipeline_id}/progress", timeout=10)
                    target_state = inspect_container(CONTAINERS[scenario["target"]])
                    probe = functional_probe(scenario["target"])
                    qdisc = qdisc_active() if code == "C5" else False
                    row = {"lower": sample_lower, "upper": time.monotonic(), "wall_utc": utc(), "progress": progress,
                           "records_in": (progress.get("spark") or {}).get("recordsIn"), "container": target_state,
                           "probe": probe, "qdisc_active": qdisc, "manual_fault_active": context.get("manual_fault_active", False)}
                    samples.append(row)
                    latest["progress"] = progress
                    append_jsonl(run_dir / "progress_samples.jsonl", row)
                    append_jsonl(run_dir / "readiness_samples.jsonl", {"lower": sample_lower, "upper": row["upper"],
                                                                           "container": target_state, "probe": probe, "qdisc_active": qdisc})
                    if endpoint["t0"] is None and fault_dispatch is not None and fault_active_for(code, before_target, row, context):
                        endpoint["t0"] = {"lower": sample_lower, "upper": row["upper"], "wall_utc": utc(),
                                          "source": "independent campaign collector", "evidence": row}
                        append_jsonl(run_dir / "fault_events.jsonl", {"event": "fault_active", **endpoint["t0"]})
                    if endpoint["t0"] and endpoint["t1"] is None:
                        restored = row["container"].get("running") is True
                        if code in {"C1", "C2", "C3", "C4"} and restored:
                            endpoint["t1"] = {"lower": sample_lower, "upper": row["upper"], "wall_utc": utc(), "source": "container collector"}
                        elif code == "C5" and not qdisc:
                            endpoint["t1"] = {"lower": sample_lower, "upper": row["upper"], "wall_utc": utc(), "source": "tc restoration collector"}
                        elif code in {"C6", "C7"} and not context.get("manual_fault_active"):
                            endpoint["t1"] = {"lower": sample_lower, "upper": row["upper"], "wall_utc": utc(), "source": "campaign restoration collector"}
                    if endpoint["t1"] and endpoint["t2"] is None and probe.get("ok"):
                        endpoint["t2"] = {"lower": sample_lower, "upper": row["upper"], "wall_utc": utc(),
                                          "source": "independent functional readiness probe", "probe": probe}
                    if endpoint["t2"] and endpoint["t3"] is None:
                        current_records = row.get("records_in")
                        prior = next((x for x in reversed(samples[:-1]) if isinstance(x.get("records_in"), int)), None)
                        if isinstance(current_records, int) and prior and current_records > prior["records_in"] and sample_lower >= endpoint["t2"]["upper"]:
                            endpoint["t3"] = {"lower": prior["lower"], "upper": row["upper"], "wall_utc": utc(),
                                              "source": "independent application progress counter", "records_in": current_records}
                except Exception as exc:
                    append_jsonl(run_dir / "readiness_samples.jsonl", {"lower": sample_lower, "upper": time.monotonic(),
                                                                           "wall_utc": utc(), "error": f"{type(exc).__name__}: {exc}"})
                append_jsonl(run_dir / "resource_samples.jsonl", resource_sample())
                collector_stop.wait(0.5)

        collector_thread = threading.Thread(target=collect, daemon=True)
        collector_thread.start()
        start = time.monotonic()
        gate_deadline = start + FAULT_GATE_TIMEOUT
        terminal = None
        while time.monotonic() - start < RUN_TIMEOUT:
            progress = latest.get("progress") or {}
            if code == "C0" and progress.get("status") in TERMINAL:
                terminal = progress
                break
            if code != "C0" and fault_dispatch is None and active_gate(progress):
                if code == "C6":
                    path = f"/hadoop/dfs/data/chaosflow-240-storage-{run_id}"
                    context["storage_file"] = path
                    before = cmd(["docker", "exec", CONTAINERS["datanode"], "df", "-B1", "/hadoop/dfs/data"], timeout=20)
                    write = cmd(["docker", "exec", CONTAINERS["datanode"], "dd", "if=/dev/zero", f"of={path}", "bs=1M", "count=256", "status=none"], timeout=120)
                    exists = cmd(["docker", "exec", CONTAINERS["datanode"], "test", "-f", path], timeout=15)
                    context["storage_file_exists"] = write.returncode == 0 and exists.returncode == 0
                    direct_action["actions"].append({"kind": "storage_pressure", "path": path, "before_df": before.stdout,
                                                     "write_returncode": write.returncode, "exists_returncode": exists.returncode, "activated_wall_utc": utc()})
                    fault_dispatch = {"lower": time.monotonic(), "upper": time.monotonic(), "kind": scenario["fault"], "source": "campaign-owned storage command"}
                    context["manual_fault_active"] = context["storage_file_exists"]
                elif code == "C7":
                    metadata = checkpoint_metadata(checkpoint_path)
                    if not metadata:
                        if time.monotonic() > gate_deadline:
                            raise RuntimeError("checkpoint metadata did not become observable before gate deadline")
                        time.sleep(1)
                        continue
                    quarantine = metadata + ".chaosflow240-quarantine"
                    moved = hdfs_cmd(["-mv", metadata, quarantine], timeout=30)
                    verified = moved.returncode == 0 and not hdfs_path_exists(metadata) and hdfs_path_exists(quarantine)
                    context.update({"checkpoint_file": metadata, "checkpoint_quarantine": quarantine,
                                    "checkpoint_quarantined": verified, "manual_fault_active": verified})
                    direct_action["actions"].append({"kind": "checkpoint_metadata_quarantine", "source": metadata,
                                                     "quarantine": quarantine, "move_returncode": moved.returncode,
                                                     "verified": verified, "activated_wall_utc": utc()})
                    fault_dispatch = {"lower": time.monotonic(), "upper": time.monotonic(), "kind": scenario["fault"], "source": "campaign-owned HDFS command"}
                else:
                    created = api.request("POST", "experiments", {"yaml_content": experiment_yaml(run_id, scenario), "pipeline_yaml": ""})
                    experiment_id = created["experiment_id"]
                    dispatch_lower = time.monotonic()
                    triggered = api.request("POST", f"experiments/{experiment_id}/run", {"pipeline_run_id": pipeline_id})
                    dispatch_upper = time.monotonic()
                    fault_dispatch = {"lower": dispatch_lower, "upper": dispatch_upper, "kind": scenario["fault"],
                                      "experiment_id": experiment_id, "triggered": triggered, "source": "safety-gated experiment API"}
                    atomic_write(run_dir / "experiment_dispatch.json", fault_dispatch)
                atomic_write(run_dir / "fault.json", {"scenario": code, "target": scenario["target"],
                                                        "dispatch": fault_dispatch, "direct_action": direct_action})
            if fault_dispatch is not None and code in {"C6", "C7"} and context.get("manual_fault_active"):
                time.sleep(scenario["duration"])
                if code == "C6":
                    restored = cmd(["docker", "exec", CONTAINERS["datanode"], "rm", "-f", context["storage_file"]], timeout=30)
                    direct_action["restoration"] = {"kind": "storage_pressure_remove", "returncode": restored.returncode, "restored_wall_utc": utc()}
                else:
                    restored = hdfs_cmd(["-mv", context["checkpoint_quarantine"], context["checkpoint_file"]], timeout=30)
                    direct_action["restoration"] = {"kind": "checkpoint_metadata_restore", "returncode": restored.returncode,
                                                     "restored_wall_utc": utc(), "path_exists": hdfs_path_exists(context["checkpoint_file"])}
                context["manual_fault_active"] = False
                atomic_write(run_dir / "fault.json", {"scenario": code, "target": scenario["target"],
                                                        "dispatch": fault_dispatch, "direct_action": direct_action})
            current = latest.get("progress") or {}
            if current.get("status") in TERMINAL:
                if code != "C0" and fault_dispatch is None:
                    raise RuntimeError("non-control pipeline reached terminal state before fault activation")
                terminal = current
                break
            if code != "C0" and fault_dispatch is None and time.monotonic() > gate_deadline:
                raise RuntimeError("active processing gate was not reached before deadline")
            time.sleep(0.25)
        if terminal is None:
            terminal = api.request("GET", f"pipeline-runs/{pipeline_id}", timeout=20)
        collector_stop.set()
        if collector_thread:
            collector_thread.join(timeout=10)
        observer_record = stop_observer(observer, run_dir)
        event_stop.set()
        if event_process.poll() is None:
            event_process.send_signal(signal.SIGTERM)
        event_thread.join(timeout=8)

        oracle, validation = run_oracle(config, output_path)
        endpoint["t5"] = {"lower": time.monotonic(), "upper": time.monotonic(), "wall_utc": utc(),
                           "source": "independent oracle and validator completion", "oracle_exit_code": oracle.get("exit_code"),
                           "validation_exit_code": validation.get("exit_code")}
        atomic_write(run_dir / "oracle.json", oracle)
        atomic_write(run_dir / "production_validation.json", validation)
        atomic_write(run_dir / "oracle_retry_evidence.json", {"attempts": oracle.get("retry_attempts", [])})
        if len(oracle.get("retry_attempts", [])) > 1 or oracle.get("exit_code") != 0 or validation.get("exit_code") != 0:
            capture_hdfs_diagnostics(output_path, run_dir)
        recovery = {"clock": "host monotonic per attempt; interval endpoints retained", "T0": endpoint["t0"],
                    "T1": endpoint["t1"], "T2": endpoint["t2"], "T3": endpoint["t3"], "T5": endpoint["t5"],
                    "T4": throughput_endpoint(samples, endpoint["t2"], baseline_rate), "scenario": code,
                    "observer_state": slot["observer_state"]}
        atomic_write(run_dir / "recovery_evidence.json", recovery)
        cleanup = cleanup_run(output_path, checkpoint_path, run_id, run_dir, context)
        observer_ok = slot["observer_state"] != "OBSERVER_ON" or (
            observer_record.get("observer_started_ok") is True and "evidence" in observer_record
        )
        instrumentation_ok = (code == "C0" or all(endpoint[key] is not None for key in ("t0", "t1", "t2", "t3"))) and observer_ok
        exposure_ok = code == "C0" or (instrumentation_ok and cleanup["completed"])
        oracle_report = oracle.get("report") or {}
        validation_report = validation.get("report") or {}
        validation_complete = "report" in oracle and "report" in validation
        correctness_ok = (
            (terminal or {}).get("status") == "succeeded"
            and oracle.get("exit_code") == 0
            and oracle_report.get("output_correct") is True
            and validation.get("exit_code") == 0
            and validation_report.get("output_correct") is True
            and validation_report.get("validation_passed") is True
        )
        status = ("PILOT_VALID" if exposure_ok and correctness_ok else "PILOT_INVALID") if mode == "pilot" else ("QUALIFYING" if exposure_ok and correctness_ok else "INVALID")
        result = {"attempt_id": run_id, "mode": mode, "slot": slot, "scenario": code, "scenario_name": scenario["name"],
                  "observer_state": slot["observer_state"], "pipeline_id": pipeline_id, "terminal_status": (terminal or {}).get("status"),
                  "status": status, "fault_exposure_ok": exposure_ok, "validation_complete": validation_complete,
                  "instrumentation_ok": instrumentation_ok,
                  "observer_ok": observer_ok,
                  "correctness_ok": correctness_ok,
                  "oracle_output_correct": (oracle.get("report") or {}).get("output_correct"), "oracle_exit_code": oracle.get("exit_code"),
                  "validation_exit_code": validation.get("exit_code"), "recovery": recovery, "directory": str(run_dir),
                  "completed_wall_utc": utc(), "output_path": output_path, "checkpoint_path": checkpoint_path, "cleanup": cleanup}
        atomic_write(run_dir / "attempt_status.json", result)
        checksums = {}
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and path.name != "checksums.json":
                checksums[str(path.relative_to(run_dir))] = digest(path)
        atomic_write(run_dir / "checksums.json", checksums)
        return result
    except Exception as exc:
        collector_stop.set()
        if collector_thread:
            collector_thread.join(timeout=10)
        stop_observer(observer, run_dir)
        event_stop.set()
        if event_process.poll() is None:
            event_process.send_signal(signal.SIGTERM)
        event_thread.join(timeout=8)
        result = {"attempt_id": run_id, "mode": mode, "slot": slot, "scenario": code,
                  "observer_state": slot["observer_state"], "pipeline_id": pipeline_id,
                  "status": "PILOT_INVALID" if mode == "pilot" else "INVALID",
                  "reason": f"{type(exc).__name__}: {exc}", "completed_wall_utc": utc(), "directory": str(run_dir)}
        atomic_write(run_dir / "attempt_status.json", result)
        atomic_write(run_dir / "failure.json", result)
        return result


def load_attempts(directory: Path) -> list[dict]:
    result = []
    for status_path in sorted(directory.glob("*/attempt_status.json")):
        try:
            result.append(json.loads(status_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return result


def strict_accepted_attempt(attempt: dict, mode: str) -> bool:
    if attempt.get("correctness_ok") is not True:
        return False
    if mode == "pilot":
        if attempt.get("status") != "PILOT_VALID":
            return False
    elif attempt.get("status") != "QUALIFYING":
        return False
    if attempt.get("observer_state") == "OBSERVER_ON" and attempt.get("observer_ok") is not True:
        return False
    if attempt.get("scenario") != "C0":
        recovery = attempt.get("recovery") or {}
        if not all(recovery.get(key) is not None for key in ("T0", "T1", "T2", "T3")):
            return False
    return True


def connect_api(env: dict[str, str], timeout: float = 180) -> Api:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            return Api(env["ADMIN_USERNAME"], env["ADMIN_PASSWORD"])
        except Exception as exc:
            last = exc
            time.sleep(3)
    raise RuntimeError(f"campaign API did not become reachable: {last}")


def write_progress(*, mode: str, current: dict | None, schedule: list[dict], attempts: list[dict], phase: str, last_event: str) -> None:
    qualifying = [a for a in attempts if strict_accepted_attempt(a, "main")]
    pilot_valid = [a for a in attempts if strict_accepted_attempt(a, "pilot")]
    invalid = [a for a in attempts if a.get("status") in {"INVALID", "PILOT_INVALID"}
               or (a.get("status") in {"QUALIFYING", "PILOT_VALID"} and a.get("correctness_ok") is not True)]
    state = {"campaign": "ChaosFlow Research Campaign", "mode": mode, "planned_qualifying_runs": 240,
             "phase": phase, "current": current, "completed_qualifying_runs": len(qualifying),
             "pilot_valid_runs": len(pilot_valid), "invalid_attempts": len(invalid), "attempt_count": len(attempts),
             "remaining_slots": max(0, 240 - len(qualifying)) if mode == "main" else None,
             "last_event": last_event, "updated_wall_utc": utc(),
             "slot_status_counts": {status: sum(1 for row in schedule if row.get("status") == status)
                                    for status in {row.get("status") for row in schedule}}}
    atomic_write(RUNTIME / "progress.json", state)
    with (RUNTIME / "progress.log").open("a", encoding="utf-8") as stream:
        stream.write(f"{state['updated_wall_utc']} phase={phase} mode={mode} qualifying={len(qualifying)} "
                     f"invalid={len(invalid)} attempts={len(attempts)} event={last_event}\n")
    print("=" * 64)
    print("CHAOSFLOW RESEARCH CAMPAIGN")
    print(f"MODE: {mode}   QUALIFYING: {len(qualifying)} / {240 if mode == 'main' else 16}")
    print(f"PHASE: {phase}   ATTEMPTS: {len(attempts)}   INVALID: {len(invalid)}")
    if current:
        print(f"SLOT: {current.get('slot')}   SCENARIO: {current.get('scenario')}   OBSERVER: {current.get('observer_state')}")
    print(f"LAST EVENT: {last_event}")
    print("=" * 64, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pilot", action="store_true")
    group.add_argument("--main", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="maximum new slots in this process")
    parser.add_argument("--skip-stack", action="store_true")
    parser.add_argument("--retry-limit", type=int, default=3,
                        help="maximum preserved attempts per slot before stopping (default: 3)")
    args = parser.parse_args()
    mode = "pilot" if args.pilot else "main"
    schedule_path = RUNTIME / ("pilot_schedule.csv" if args.pilot else "run_schedule.csv")
    schedule = make_schedule(schedule_path, pilot=args.pilot)
    attempts_dir = RUNTIME / ("pilot_attempts" if args.pilot else "attempts")
    attempts_dir.mkdir(exist_ok=True)
    with (RUNTIME / "campaign.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not args.skip_stack:
            ensure_stack()
        env = dotenv(ROOT / ".env")
        api = connect_api(env)
        all_attempts = load_attempts(attempts_dir)
        baseline_rate = None
        baseline_path = RUNTIME / "pilot_baseline.json"
        if baseline_path.exists():
            baseline_rate = json.loads(baseline_path.read_text(encoding="utf-8")).get("baseline_rate")
        processed = 0
        for row in schedule:
            if row.get("status") in {"QUALIFYING", "PILOT_VALID"}:
                continue
            if args.limit is not None and processed >= args.limit:
                break
            healthy, _ = project_healthy()
            if not healthy:
                raise RuntimeError("resource/safety gate: campaign project is not healthy")
            resources = resource_sample()
            if resources["available_memory"] < MIN_AVAILABLE_MEMORY or resources["campaign_disk_free"] < MIN_CAMPAIGN_DISK:
                raise RuntimeError(f"resource/safety gate: {resources}")
            run_id = "c240-" + datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S") + "-" + uuid.uuid4().hex[:10]
            run_dir = attempts_dir / run_id
            run_dir.mkdir()
            write_progress(mode=mode, current=row, schedule=schedule, attempts=all_attempts,
                           phase="STARTING_ATTEMPT", last_event=f"starting {run_id}")
            result = run_attempt(api, dict(row), run_dir, mode=mode, baseline_rate=baseline_rate)
            all_attempts.append(result)
            row["attempt_ids"] = ";".join(x for x in [row.get("attempt_ids", ""), run_id] if x)
            row["status"] = result["status"]
            destination = RUNTIME / ("qualifying_runs" if result["status"] in {"QUALIFYING", "PILOT_VALID"} else "invalid_attempts")
            destination.mkdir(exist_ok=True)
            atomic_write(destination / f"{run_id}.json", result)
            update_schedule(schedule_path, schedule)
            write_progress(mode=mode, current=row, schedule=schedule, attempts=all_attempts,
                           phase="ATTEMPT_COMPLETE", last_event=f"{run_id} -> {result['status']}")
            processed += 1
            if result["status"] in {"INVALID", "PILOT_INVALID"}:
                retry_count = len([a for a in all_attempts if a.get("slot", {}).get("slot") == row.get("slot")])
                if retry_count >= args.retry_limit:
                    raise RuntimeError(f"systematic failure: slot {row.get('slot')} reached retry limit {args.retry_limit}")
                row["status"] = "RETRY_REQUIRED"
                update_schedule(schedule_path, schedule)
        write_progress(mode=mode, current=None, schedule=schedule, attempts=all_attempts,
                       phase="PAUSED_OR_COMPLETE", last_event="runner reached requested limit or schedule end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
