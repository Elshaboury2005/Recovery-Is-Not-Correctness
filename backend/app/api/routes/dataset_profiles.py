"""Authenticated dataset discovery and profiling APIs."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.dataset_profile import DatasetProfile
from app.schemas.profiling import (
    ProfileComparisonResponse,
    ProfileCreateRequest,
    ProfileJobResponse,
    ProfileResponse,
)
from app.services.dataset_profile_service import (
    allowed_profile_roots,
    compare_profiles,
    profile_row_to_dict,
    run_profile_job,
    validate_profile_source,
)

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("/discover")
async def discover_datasets(_: str = Depends(get_current_user)) -> list[dict]:
    """List files in configured roots without reading their contents."""
    items: list[dict] = []
    for root in allowed_profile_roots():
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".jsonl", ".ndjson", ".parquet"}:
                continue
            items.append({
                "name": path.name,
                "source_uri": str(path),
                "format": path.suffix.lower().lstrip("."),
                "size_bytes": path.stat().st_size,
            })
    return items


@router.post("/profiles", response_model=ProfileJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_profile(
    request: ProfileCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ProfileJobResponse:
    try:
        validate_profile_source(request.source_uri)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dataset_name = request.dataset_name or Path(request.source_uri).stem
    latest = await db.scalar(
        select(func.max(DatasetProfile.profile_version)).where(DatasetProfile.dataset_name == dataset_name)
    )
    row = DatasetProfile(
        dataset_name=dataset_name,
        source_uri=request.source_uri,
        status="queued",
        progress=0,
        profile_version=int(latest or 0) + 1,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    profile_id = str(row.id)
    asyncio.create_task(
        asyncio.to_thread(run_profile_job, profile_id, request.source_uri, request.sample_rows),
        name=f"dataset-profile-{profile_id}",
    )
    return ProfileJobResponse(
        profile_id=profile_id,
        dataset_name=dataset_name,
        status="queued",
        progress=0,
    )


@router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ProfileResponse]:
    rows = (
        await db.scalars(
            select(DatasetProfile)
            .order_by(DatasetProfile.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [ProfileResponse.model_validate(profile_row_to_dict(row)) for row in rows]


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: str = Depends(get_current_user),
) -> ProfileResponse:
    try:
        row = await db.get(DatasetProfile, uuid.UUID(profile_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileResponse.model_validate(profile_row_to_dict(row))


@router.get("/profiles/{profile_id}/compare", response_model=ProfileComparisonResponse)
async def compare_profile_versions(
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    other_id: str = Query(...),
    _: str = Depends(get_current_user),
) -> ProfileComparisonResponse:
    try:
        left_id = uuid.UUID(profile_id)
        right_id = uuid.UUID(other_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc
    left = await db.get(DatasetProfile, left_id)
    right = await db.get(DatasetProfile, right_id)
    if left is None or right is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileComparisonResponse(
        left_profile_id=profile_id,
        right_profile_id=other_id,
        changes=compare_profiles(left, right),
    )
