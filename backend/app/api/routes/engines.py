"""Engine capability and health endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.engines import get_engine_adapter, list_engine_capabilities
from app.engines.models import EngineName

router = APIRouter(prefix="/api/engines", tags=["engines"])


@router.get("/capabilities")
async def engine_capabilities(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Return static capability declarations without claiming runtime readiness."""
    return list_engine_capabilities()


@router.get("/health")
async def engine_health(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Return live health for each registered engine plus its capabilities."""
    adapters = [get_engine_adapter("spark"), get_engine_adapter("flink")]
    results = await asyncio.gather(*(adapter.health_check() for adapter in adapters))
    return [
        {
            "capability": adapter.capability().model_copy(update={"available": bool(health.get("connected"))}),
            "health": health,
        }
        for adapter, health in zip(adapters, results, strict=True)
    ]


@router.get("/{engine}/capabilities")
async def one_engine_capabilities(engine: EngineName, _: str = Depends(get_current_user)) -> dict[str, Any]:
    """Return one static engine capability declaration."""
    try:
        return get_engine_adapter(engine).capability().model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{engine}/health")
async def one_engine_health(engine: EngineName, _: str = Depends(get_current_user)) -> dict[str, Any]:
    """Return one engine's live health result."""
    try:
        adapter = get_engine_adapter(engine)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"capability": adapter.capability().model_dump(), "health": await adapter.health_check()}
