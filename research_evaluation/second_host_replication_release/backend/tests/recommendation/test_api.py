from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_recommendation_routes_require_authentication() -> None:
    assert TestClient(app).get("/api/recommendations").status_code == 401
