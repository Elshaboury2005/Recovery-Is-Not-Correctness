from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_engine_chaos_capabilities_require_authentication() -> None:
    assert TestClient(app).get("/api/chaoslab/engine-capabilities").status_code == 401


def test_flink_is_not_fault_injection_ready_without_runtime() -> None:
    class Adapter:
        async def health_check(self):
            return {"connected": False, "status": "UNREACHABLE"}

    with patch("app.reliability.engine_chaos.get_engine_adapter", return_value=Adapter()):
        import asyncio
        from app.reliability.engine_chaos import engine_chaos_capabilities

        result = asyncio.run(engine_chaos_capabilities())

    assert result[0]["ready_for_fault_injection"] is False
    assert result[1]["ready_for_fault_injection"] is False
