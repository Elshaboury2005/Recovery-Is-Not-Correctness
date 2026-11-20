"""Authenticated safe reconfiguration proposal and approval APIs."""

from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.engines.registry import get_engine_adapter
from app.models.architecture_recommendation import ArchitectureRecommendation
from app.models.reconfiguration import ReconfigurationOperation
from app.metrics import transformation_reconfiguration_events_total
from app.reconfiguration.state import ReconfigurationStateError, preflight_recommendation, transition
from app.schemas.reconfiguration import ReconfigurationCreateRequest, ReconfigurationResponse, ReconfigurationStateResponse
from app.services.reconfiguration_service import run_reconfiguration

router = APIRouter(prefix="/api/reconfigurations", tags=["reconfigurations"])


def _event(action: str, state: str, detail: str) -> dict:
    return {"action": action, "state": state, "detail": detail, "timestamp": datetime.now(timezone.utc).isoformat()}


def _response(row: ReconfigurationOperation) -> ReconfigurationResponse:
    return ReconfigurationResponse(
        operation_id=str(row.id), recommendation_id=str(row.recommendation_id), current_engine=row.current_engine,
        target_engine=row.target_engine, state=row.state, requested_overrides=row.requested_overrides,
        preflight_evidence=row.preflight_evidence, audit_events=row.audit_events,
        execution_result=row.execution_result, error_message=row.error_message,
    )


async def _get_operation(db: AsyncSession, operation_id: str) -> ReconfigurationOperation:
    try:
        row = await db.get(ReconfigurationOperation, uuid.UUID(operation_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Reconfiguration operation not found") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Reconfiguration operation not found")
    return row


@router.post("", response_model=ReconfigurationResponse, status_code=status.HTTP_201_CREATED)
async def propose_reconfiguration(
    request: ReconfigurationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ReconfigurationResponse:
    try:
        recommendation_id = uuid.UUID(request.recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Recommendation not found") from exc
    recommendation = await db.get(ArchitectureRecommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    target_engine = request.target_engine or recommendation.selected_engine
    if not target_engine:
        raise HTTPException(status_code=409, detail="Recommendation has no selected engine")
    if request.target_engine and request.target_engine != recommendation.selected_engine:
        measured_targets = {
            str(item.get("engine"))
            for item in (recommendation.result or {}).get("supporting_benchmark_measurements", [])
            if item.get("successful_measured_runs", 0) > 0 and item.get("correctness_status", "passed") in {"passed", "PASS"}
        }
        if request.target_engine not in measured_targets:
            raise HTTPException(status_code=409, detail="Engine override requires correctness-passed measured evidence for this workload")
    row = ReconfigurationOperation(
        recommendation_id=recommendation.id, current_engine=request.current_engine, target_engine=target_engine,
        state="proposed", requested_overrides=request.overrides, preflight_evidence={}, audit_events=[], execution_result={}
    )
    row.audit_events = [_event("proposed", "proposed", "Proposal created; no runtime mutation was applied.")]
    db.add(row)
    await db.flush()
    transformation_reconfiguration_events_total.labels(engine=target_engine, state="proposed").inc()
    return _response(row)


@router.get("", response_model=list[ReconfigurationResponse])
async def list_reconfigurations(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> list[ReconfigurationResponse]:
    rows = (await db.scalars(select(ReconfigurationOperation).order_by(ReconfigurationOperation.created_at.desc()))).all()
    return [_response(row) for row in rows]


@router.post("/{operation_id}/preflight", response_model=ReconfigurationResponse)
async def preflight(
    operation_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ReconfigurationResponse:
    row = await _get_operation(db, operation_id)
    if row.state != "proposed":
        raise HTTPException(status_code=409, detail=f"Preflight requires proposed state, got {row.state}")
    recommendation = await db.get(ArchitectureRecommendation, row.recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=409, detail="Recommendation no longer exists")
    health = await get_engine_adapter(row.target_engine).health_check()
    evidence = preflight_recommendation(
        {"status": recommendation.status, "selected_engine": recommendation.selected_engine, "result": recommendation.result},
        target_health=health, current_engine=row.current_engine, target_engine=row.target_engine, overrides=row.requested_overrides,
    )
    row.preflight_evidence = evidence
    target_state = "preflight_passed" if evidence["status"] == "passed" else "blocked"
    row.state = transition(row.state, target_state)
    row.audit_events = [*row.audit_events, _event("preflight", row.state, evidence["status"])]
    await db.flush()
    transformation_reconfiguration_events_total.labels(engine=row.target_engine, state=row.state).inc()
    return _response(row)


@router.post("/{operation_id}/approve", response_model=ReconfigurationStateResponse)
async def approve(
    operation_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ReconfigurationStateResponse:
    row = await _get_operation(db, operation_id)
    try:
        row.state = transition(row.state, "approved")
    except ReconfigurationStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    row.audit_events = [*row.audit_events, _event("approved", row.state, "Explicit approval recorded; execution remains a separate action.")]
    await db.flush()
    transformation_reconfiguration_events_total.labels(engine=row.target_engine, state=row.state).inc()
    return ReconfigurationStateResponse(operation_id=operation_id, state=row.state)


@router.post("/{operation_id}/execute", response_model=ReconfigurationStateResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute(
    operation_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ReconfigurationStateResponse:
    row = await _get_operation(db, operation_id)
    try:
        row.state = transition(row.state, "executing")
    except ReconfigurationStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    row.error_message = None
    row.execution_result = {"status": "queued", "deployment_mode": "isolated_verification", "production_mutation_applied": False}
    row.audit_events = [*row.audit_events, _event("execution_started", row.state, "Approved operation queued for isolated verification; production routing is unchanged.")]
    await db.commit()
    transformation_reconfiguration_events_total.labels(engine=row.target_engine, state=row.state).inc()
    asyncio.create_task(asyncio.to_thread(run_reconfiguration, operation_id), name=f"reconfiguration-{operation_id}")
    return ReconfigurationStateResponse(operation_id=operation_id, state=row.state)


@router.post("/{operation_id}/rollback", response_model=ReconfigurationStateResponse)
async def rollback(
    operation_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ReconfigurationStateResponse:
    row = await _get_operation(db, operation_id)
    try:
        row.state = transition(row.state, "rolled_back")
    except ReconfigurationStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    row.execution_result = {
        **row.execution_result,
        "rollback": {
            "status": "recorded",
            "scope": "no_production_mutation",
            "evidence_retained": True,
            "detail": "The isolated verification output was retained; no live routing change required reversal.",
        },
    }
    row.audit_events = [*row.audit_events, _event("rollback_recorded", row.state, "Rollback boundary recorded; isolated evidence retained.")]
    await db.flush()
    transformation_reconfiguration_events_total.labels(engine=row.target_engine, state=row.state).inc()
    return ReconfigurationStateResponse(operation_id=operation_id, state=row.state)


@router.get("/{operation_id}", response_model=ReconfigurationResponse)
async def get_reconfiguration(
    operation_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ReconfigurationResponse:
    return _response(await _get_operation(db, operation_id))
