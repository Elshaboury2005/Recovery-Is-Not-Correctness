from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = create_access_token({"sub": "admin"}, timedelta(minutes=15))
    return {"Authorization": f"Bearer {token}"}


def test_engine_capabilities_requires_auth() -> None:
    response = TestClient(app).get("/api/engines/capabilities")
    assert response.status_code == 401


def test_engine_health_reports_dynamic_availability(auth_headers: dict[str, str]) -> None:
    with patch("app.api.routes.engines.get_engine_adapter") as get_adapter:
        spark = get_adapter.return_value
        spark.capability.return_value = type("Capability", (), {
            "model_copy": lambda self, update: {"engine": "spark", **update},
            "model_dump": lambda self: {"engine": "spark"},
        })()
        spark.health_check = AsyncMock(return_value={"connected": True})
        flink = type("Flink", (), {})()
        flink.capability = lambda: type("Capability", (), {
            "model_copy": lambda self, update: {"engine": "flink", **update},
            "model_dump": lambda self: {"engine": "flink"},
        })()
        flink.health_check = AsyncMock(return_value={"connected": False})
        get_adapter.side_effect = [spark, flink]
        response = TestClient(app).get("/api/engines/health", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["health"]["connected"] is True
    assert payload[1]["health"]["connected"] is False
