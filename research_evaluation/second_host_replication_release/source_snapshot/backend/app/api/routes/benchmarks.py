"""Authenticated benchmark campaign and comparison APIs."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.benchmark.planner import BenchmarkPlanner
from app.database.session import get_db
from app.models.benchmark_campaign import BenchmarkCampaign
from app.models.workload_definition import WorkloadDefinition
from app.schemas.benchmark import (
    BenchmarkCampaignResponse,
    BenchmarkCreateRequest,
    BenchmarkDetailResponse,
    BenchmarkExecuteResponse,
    BenchmarkRunResponse,
)
from app.services.benchmark_service import comparison_for_campaign, run_benchmark_campaign

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])
_planner = BenchmarkPlanner()


def _run_response(run) -> BenchmarkRunResponse:
    return BenchmarkRunResponse(
        run_id=str(run.id), engine=run.engine, repetition=run.repetition, is_warmup=run.is_warmup,
        status=run.status, configuration=run.configuration, metrics=run.metrics,
        resource_metrics=run.resource_metrics, correctness=run.correctness,
        software_versions=run.software_versions, error_message=run.error_message,
    )


def _campaign_response(campaign: BenchmarkCampaign) -> BenchmarkCampaignResponse:
    return BenchmarkCampaignResponse(
        campaign_id=str(campaign.id), name=campaign.name, status=campaign.status,
        workload_id=str(campaign.workload_definition_id), plan=campaign.plan,
        fairness_contract=campaign.fairness_contract, error_message=campaign.error_message,
    )


@router.post("", response_model=BenchmarkCampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_benchmark(
    request: BenchmarkCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> BenchmarkCampaignResponse:
    try:
        workload_id = uuid.UUID(request.workload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Workload definition not found") from exc
    workload = await db.get(WorkloadDefinition, workload_id)
    if workload is None:
        raise HTTPException(status_code=404, detail="Workload definition not found")
    try:
        plan = _planner.generate(
            workload.classification,
            candidates=request.candidates,
            repetitions=request.repetitions,
            warmup_runs=request.warmup_runs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    campaign = BenchmarkCampaign(
        name=request.name or f"benchmark-{workload.name}",
        workload_definition_id=workload.id,
        dataset_profile_id=workload.dataset_profile_id,
        status="planned",
        repetitions=request.repetitions,
        warmup_runs=request.warmup_runs,
        plan=plan,
        fairness_contract=plan["fairness_contract"],
    )
    db.add(campaign)
    await db.flush()
    return _campaign_response(campaign)


@router.get("", response_model=list[BenchmarkCampaignResponse])
async def list_benchmarks(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> list[BenchmarkCampaignResponse]:
    rows = (await db.scalars(select(BenchmarkCampaign).order_by(BenchmarkCampaign.created_at.desc()))).all()
    return [_campaign_response(row) for row in rows]


@router.post("/{campaign_id}/execute", response_model=BenchmarkExecuteResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_benchmark(
    campaign_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> BenchmarkExecuteResponse:
    try:
        campaign = await db.get(BenchmarkCampaign, uuid.UUID(campaign_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Benchmark campaign not found") from exc
    if campaign is None:
        raise HTTPException(status_code=404, detail="Benchmark campaign not found")
    if campaign.status != "planned":
        raise HTTPException(status_code=409, detail=f"Campaign is already {campaign.status}")
    campaign.status = "queued"
    await db.commit()
    asyncio.create_task(asyncio.to_thread(run_benchmark_campaign, campaign_id), name=f"benchmark-{campaign_id}")
    return BenchmarkExecuteResponse(campaign_id=campaign_id, status="queued")


@router.get("/{campaign_id}/comparison")
async def benchmark_comparison(
    campaign_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> dict:
    try:
        campaign = await db.scalar(
            select(BenchmarkCampaign).options(selectinload(BenchmarkCampaign.runs)).where(BenchmarkCampaign.id == uuid.UUID(campaign_id))
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Benchmark campaign not found") from exc
    if campaign is None:
        raise HTTPException(status_code=404, detail="Benchmark campaign not found")
    return {"campaign_id": campaign_id, "comparison": comparison_for_campaign(campaign)}


@router.get("/{campaign_id}", response_model=BenchmarkDetailResponse)
async def benchmark_detail(
    campaign_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> BenchmarkDetailResponse:
    try:
        campaign = await db.scalar(
            select(BenchmarkCampaign).options(selectinload(BenchmarkCampaign.runs)).where(BenchmarkCampaign.id == uuid.UUID(campaign_id))
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Benchmark campaign not found") from exc
    if campaign is None:
        raise HTTPException(status_code=404, detail="Benchmark campaign not found")
    base = _campaign_response(campaign)
    return BenchmarkDetailResponse(**base.model_dump(), runs=[_run_response(run) for run in campaign.runs], comparison=comparison_for_campaign(campaign))
