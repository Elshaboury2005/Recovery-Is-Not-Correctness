"""Authenticated workload classification APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.dataset_profile import DatasetProfile
from app.models.workload_definition import WorkloadDefinition
from app.metrics import transformation_workload_classifications_total
from app.pipeline.exceptions import ConfigParseError, ConfigValidationError
from app.pipeline.parser import PipelineConfigParser
from app.pipeline.validator import PipelineBusinessValidator
from app.schemas.workload import WorkloadClassifyRequest, WorkloadClassifyResponse, WorkloadResponse
from app.workload.classifier import WorkloadClassifier

router = APIRouter(prefix="/api/workloads", tags=["workloads"])
_parser = PipelineConfigParser()
_validator = PipelineBusinessValidator()


def _response(row: WorkloadDefinition) -> WorkloadResponse:
    return WorkloadResponse(
        workload_id=str(row.id),
        name=row.name,
        dataset_profile_id=str(row.dataset_profile_id) if row.dataset_profile_id else None,
        constraints=row.constraints,
        classification=row.classification,
        created_at=row.created_at,
    )


@router.get("", response_model=list[WorkloadResponse])
async def list_workloads(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> list[WorkloadResponse]:
    rows = (
        await db.scalars(
            select(WorkloadDefinition)
            .order_by(WorkloadDefinition.created_at.desc())
            .limit(100)
        )
    ).all()
    return [_response(row) for row in rows]


@router.post("/classify", response_model=WorkloadClassifyResponse)
async def classify_workload(
    request: WorkloadClassifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> WorkloadClassifyResponse:
    try:
        config = _parser.parse_string(request.pipeline_yaml)
    except (ConfigParseError, ConfigValidationError) as exc:
        errors = exc.errors if isinstance(exc, ConfigValidationError) else [{"field": "yaml", "message": str(exc)}]
        raise HTTPException(status_code=422, detail=errors) from exc
    validation_errors = _validator.validate(config)
    if validation_errors:
        raise HTTPException(status_code=422, detail=validation_errors)

    profile_result = None
    profile_uuid = None
    if request.dataset_profile_id:
        try:
            profile_uuid = uuid.UUID(request.dataset_profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Dataset profile not found") from exc
        profile = await db.get(DatasetProfile, profile_uuid)
        if profile is None or profile.status != "succeeded" or not profile.result:
            raise HTTPException(status_code=409, detail="Dataset profile is not available yet")
        profile_result = profile.result

    classification = WorkloadClassifier().classify(config, profile_result, request.constraints)
    name = request.name or config.pipeline.name
    row = WorkloadDefinition(
        name=name,
        pipeline_yaml=request.pipeline_yaml,
        dataset_profile_id=profile_uuid,
        constraints=request.constraints,
        classification=classification,
    )
    db.add(row)
    await db.flush()
    categories = classification.get("categories") or ["unknown"]
    transformation_workload_classifications_total.labels(primary_category=str(categories[0])).inc()
    return WorkloadClassifyResponse(workload_id=str(row.id), name=name, classification=classification)
