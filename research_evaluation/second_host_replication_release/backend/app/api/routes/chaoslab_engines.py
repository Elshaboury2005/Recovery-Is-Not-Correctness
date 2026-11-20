"""Engine-specific ChaosLab readiness API."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.reliability.engine_chaos import engine_chaos_capabilities

router = APIRouter(prefix="/api/chaoslab", tags=["chaoslab"])


@router.get("/engine-capabilities")
async def capabilities(_: str = Depends(get_current_user)) -> list[dict]:
    return await engine_chaos_capabilities()
