from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = create_access_token({"sub": "admin"}, timedelta(minutes=15))
    return {"Authorization": f"Bearer {token}"}


def test_dataset_discovery_requires_auth() -> None:
    assert TestClient(app).get("/api/datasets/discover").status_code == 401


def test_dataset_discovery_returns_supported_files(auth_headers: dict[str, str]) -> None:
    response = TestClient(app).get("/api/datasets/discover", headers=auth_headers)
    assert response.status_code == 200
    assert any(item["name"] == "sales_sample.csv" for item in response.json())


def test_profile_rejects_path_outside_configured_roots(auth_headers: dict[str, str]) -> None:
    response = TestClient(app).post(
        "/api/datasets/profiles",
        headers=auth_headers,
        json={"source_uri": "/etc/passwd"},
    )
    assert response.status_code == 400
