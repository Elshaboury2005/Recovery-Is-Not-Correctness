"""Authenticated explainable architecture recommendation APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.architecture_recommendation import ArchitectureRecommendation
from app.models.benchmark_campaign import BenchmarkCampaign
from app.models.workload_definition import WorkloadDefinition
from app.metrics import transformation_recommendations_total
from app.recommendation.engine import RecommendationEngine
from app.schemas.recommendation import RecommendationCreateRequest, RecommendationResponse
from app.services.benchmark_service import comparison_for_campaign

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])
_engine = RecommendationEngine()


def _response(row: ArchitectureRecommendation) -> RecommendationResponse:
    return RecommendationResponse(
        recommendation_id=str(row.id), workload_id=str(row.workload_definition_id),
        benchmark_campaign_id=str(row.benchmark_campaign_id) if row.benchmark_campaign_id else None,
        optimization_goal=row.optimization_goal, selected_engine=row.selected_engine,
        status=row.status, result=row.result,
    )


@router.post("", response_model=RecommendationResponse, status_code=201)
async def create_recommendation(
    request: RecommendationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> RecommendationResponse:
    try:
        workload_id = uuid.UUID(request.workload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Workload definition not found") from exc
    workload = await db.get(WorkloadDefinition, workload_id)
    if workload is None:
        raise HTTPException(status_code=404, detail="Workload definition not found")

    campaign = None
    comparison = None
    campaign_id = None
    if request.benchmark_campaign_id:
        try:
            campaign_id = uuid.UUID(request.benchmark_campaign_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Benchmark campaign not found") from exc
        campaign = await db.scalar(
            select(BenchmarkCampaign).options(selectinload(BenchmarkCampaign.runs)).where(BenchmarkCampaign.id == campaign_id)
        )
        if campaign is None or campaign.workload_definition_id != workload.id:
            raise HTTPException(status_code=404, detail="Benchmark campaign not found for workload")
        comparison = comparison_for_campaign(campaign)

    result = _engine.recommend(
        workload.classification,
        benchmark_comparison=comparison,
        optimization_goal=request.optimization_goal,
        resource_constraints=request.resource_constraints,
    )
    row = ArchitectureRecommendation(
        workload_definition_id=workload.id,
        benchmark_campaign_id=campaign_id,
        optimization_goal=request.optimization_goal,
        selected_engine=result["selected_engine"],
        status=result["status"],
        resource_constraints=request.resource_constraints,
        result=result,
    )
    db.add(row)
    await db.flush()
    transformation_recommendations_total.labels(
        status=str(result.get("status", "unknown")),
        optimization_goal=request.optimization_goal,
    ).inc()
    return _response(row)


@router.get("", response_model=list[RecommendationResponse])
async def list_recommendations(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> list[RecommendationResponse]:
    rows = (await db.scalars(select(ArchitectureRecommendation).order_by(ArchitectureRecommendation.created_at.desc()))).all()
    return [_response(row) for row in rows]


@router.get("/{recommendation_id}", response_model=RecommendationResponse)
async def get_recommendation(
    recommendation_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> RecommendationResponse:
    try:
        row = await db.get(ArchitectureRecommendation, uuid.UUID(recommendation_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Recommendation not found") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return _response(row)
