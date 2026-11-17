"""API-driven orchestration for the evidence-based transformation workflow.

The DAG intentionally remains a thin orchestrator. Profiling, classification,
benchmarking, recommendation, and reconfiguration safety rules stay in the
backend APIs, so Airflow only sequences them, polls durable state, and exposes
failure evidence in the task log/XCom trail.

Manual trigger configuration::

    {
      "source_uri": "/app/sample-data/sales_sample.csv",
      "pipeline_yaml": "<validated pipeline YAML>",
      "dataset_name": "sales-sample",
      "optimization_goal": "balanced",
      "resource_constraints": {},
      "repetitions": 1,
      "warmup_runs": 0
    }

The workflow ends at reconfiguration preflight. Execution remains an explicit
separate action in the authenticated API and is never performed implicitly by
an Airflow retry.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any

import requests
from airflow.decorators import dag, task
from airflow.exceptions import AirflowException
from airflow.operators.python import get_current_context


BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://backend:8000").rstrip("/")
BACKEND_USERNAME = os.environ.get("BACKEND_USERNAME", "")
BACKEND_PASSWORD = os.environ.get("BACKEND_PASSWORD", "")
POLL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 900


def _request(method: str, path: str, token: str, **kwargs: Any) -> requests.Response:
    response = requests.request(
        method,
        f"{BACKEND_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
        **kwargs,
    )
    response.raise_for_status()
    return response


def _poll(path: str, token: str, terminal: set[str], failed: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        body = _request("GET", path, token).json()
        state = str(body.get("status", body.get("state", "")))
        if state in terminal:
            return body
        if state in failed:
            raise AirflowException(f"Backend workflow state at {path} was {state}: {body}")
        time.sleep(POLL_SECONDS)
    raise AirflowException(f"Timed out waiting for backend workflow state at {path}")


@dag(
    dag_id="transformation_intelligence_dag",
    description=(
        "Profile a dataset, classify its workload, run a fair benchmark, "
        "create an evidence-backed recommendation, and preflight a safe proposal."
    ),
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "owner": "platform-team",
        "retries": 0,
        "retry_delay": timedelta(minutes=2),
        "email_on_failure": False,
        "email_on_retry": False,
    },
    tags=["platform", "transformation", "evidence", "safe-reconfiguration"],
    doc_md=__doc__,
)
def transformation_intelligence_dag():
    @task()
    def load_configuration() -> dict[str, Any]:
        context = get_current_context()
        conf = dict(context["dag_run"].conf or {})
        for key in ("source_uri", "pipeline_yaml"):
            if not conf.get(key):
                raise AirflowException(f"dag_run.conf must contain '{key}'")
        return {
            "source_uri": conf["source_uri"],
            "pipeline_yaml": conf["pipeline_yaml"],
            "dataset_name": conf.get("dataset_name"),
            "optimization_goal": conf.get("optimization_goal", "balanced"),
            "resource_constraints": conf.get("resource_constraints", {}),
            "repetitions": int(conf.get("repetitions", 1)),
            "warmup_runs": int(conf.get("warmup_runs", 0)),
        }

    @task()
    def authenticate(_: dict[str, Any]) -> str:
        if not BACKEND_USERNAME or not BACKEND_PASSWORD:
            raise AirflowException("BACKEND_USERNAME and BACKEND_PASSWORD must be configured")
        response = requests.post(
            f"{BACKEND_BASE_URL}/api/auth/login",
            data={"username": BACKEND_USERNAME, "password": BACKEND_PASSWORD},
            timeout=30,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    @task()
    def profile_dataset(config: dict[str, Any], token: str) -> dict[str, Any]:
        body = {
            "source_uri": config["source_uri"],
            "dataset_name": config.get("dataset_name"),
            "sample_rows": 10_000,
        }
        created = _request("POST", "/api/datasets/profiles", token, json=body).json()
        return _poll(
            f"/api/datasets/profiles/{created['profile_id']}",
            token,
            terminal={"succeeded"},
            failed={"failed"},
        )

    @task()
    def classify_workload(config: dict[str, Any], profile: dict[str, Any], token: str) -> dict[str, Any]:
        return _request(
            "POST",
            "/api/workloads/classify",
            token,
            json={
                "name": config.get("dataset_name"),
                "pipeline_yaml": config["pipeline_yaml"],
                "dataset_profile_id": profile["profile_id"],
                "constraints": {},
            },
        ).json()

    @task()
    def benchmark(config: dict[str, Any], workload: dict[str, Any], token: str) -> dict[str, Any]:
        campaign = _request(
            "POST",
            "/api/benchmarks",
            token,
            json={
                "workload_id": workload["workload_id"],
                "repetitions": config["repetitions"],
                "warmup_runs": config["warmup_runs"],
            },
        ).json()
        _request("POST", f"/api/benchmarks/{campaign['campaign_id']}/execute", token)
        return _poll(
            f"/api/benchmarks/{campaign['campaign_id']}",
            token,
            terminal={"succeeded"},
            failed={"failed", "cancelled"},
        )

    @task()
    def recommend(config: dict[str, Any], workload: dict[str, Any], campaign: dict[str, Any], token: str) -> dict[str, Any]:
        return _request(
            "POST",
            "/api/recommendations",
            token,
            json={
                "workload_id": workload["workload_id"],
                "benchmark_campaign_id": campaign["campaign_id"],
                "optimization_goal": config["optimization_goal"],
                "resource_constraints": config["resource_constraints"],
            },
        ).json()

    @task()
    def preflight(recommendation: dict[str, Any], token: str) -> dict[str, Any]:
        operation = _request(
            "POST",
            "/api/reconfigurations",
            token,
            json={"recommendation_id": recommendation["recommendation_id"]},
        ).json()
        return _request(
            "POST",
            f"/api/reconfigurations/{operation['operation_id']}/preflight",
            token,
        ).json()

    config = load_configuration()
    token = authenticate(config)
    profile = profile_dataset(config, token)
    workload = classify_workload(config, profile, token)
    campaign = benchmark(config, workload, token)
    recommendation = recommend(config, workload, campaign, token)
    preflight(recommendation, token)


transformation_intelligence_dag()
