"""Read-only infrastructure topology API."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.infrastructure.topology import compare_topology, discover_topology
from app.models.architecture_recommendation import ArchitectureRecommendation

router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])


@router.get("/topology")
async def topology(_: str = Depends(get_current_user)) -> dict:
    return discover_topology()


@router.get("/comparison")
async def topology_comparison(
    db: Annotated[AsyncSession, Depends(get_db)],
    recommendation_id: str | None = None,
    _: str = Depends(get_current_user),
) -> dict:
    recommendation = None
    if recommendation_id:
        try:
            recommendation = await db.get(ArchitectureRecommendation, uuid.UUID(recommendation_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Recommendation not found") from exc
        if recommendation is None:
            raise HTTPException(status_code=404, detail="Recommendation not found")
    return compare_topology(discover_topology(), recommendation)
