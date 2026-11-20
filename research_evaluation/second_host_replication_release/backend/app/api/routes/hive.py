"""Authenticated Hive health and read-only SQL Explorer APIs."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.hive.sql import HiveSqlValidationError, validate_read_only_sql
from app.models.hive_query import HiveQueryHistory
from app.schemas.hive import HiveQueryRequest, HiveQueryResponse, HiveTableRegistrationRequest, HiveTableResponse
from app.services.hive_service import HiveUnavailableError, describe_table, execute_read_only, hive_health, list_tables, register_external_parquet_table

router = APIRouter(prefix="/api/hive", tags=["hive"])


def _response(row: HiveQueryHistory) -> HiveQueryResponse:
    return HiveQueryResponse(query_id=str(row.id), sql=row.sql_text, status=row.status, row_count=row.row_count, columns=row.columns, rows=row.rows, duration_ms=row.duration_ms, error_message=row.error_message)


@router.get("/health")
async def health(_: str = Depends(get_current_user)) -> dict:
    return await hive_health()


@router.get("/tables", response_model=list[HiveTableResponse])
async def tables(_: str = Depends(get_current_user)) -> list[HiveTableResponse]:
    try:
        names = await asyncio.to_thread(list_tables)
    except HiveUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Hive metadata discovery failed: {exc}") from exc
    return [HiveTableResponse(table_name=name) for name in names]


@router.post("/tables", response_model=HiveTableResponse, status_code=201)
async def register_table(request: HiveTableRegistrationRequest, _: str = Depends(get_current_user)) -> HiveTableResponse:
    try:
        await asyncio.to_thread(register_external_parquet_table, request.table_name, request.location, [column.model_dump() for column in request.columns])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HiveUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Hive table registration failed: {exc}") from exc
    return HiveTableResponse(table_name=request.table_name)


@router.get("/tables/{table_name}", response_model=HiveTableResponse)
async def table_schema(table_name: str, _: str = Depends(get_current_user)) -> HiveTableResponse:
    try:
        columns = await asyncio.to_thread(describe_table, table_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HiveUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Hive schema inspection failed: {exc}") from exc
    return HiveTableResponse(table_name=table_name, columns=columns)


@router.post("/queries", response_model=HiveQueryResponse, status_code=202)
async def query(request: HiveQueryRequest, db: Annotated[AsyncSession, Depends(get_db)], _: str = Depends(get_current_user)) -> HiveQueryResponse:
    try:
        sql = validate_read_only_sql(request.sql)
    except HiveSqlValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = HiveQueryHistory(sql_text=sql, status="queued", started_at=datetime.now(timezone.utc))
    db.add(row)
    await db.flush()
    try:
        result = await asyncio.to_thread(execute_read_only, sql, max_rows=request.max_rows)
        row.status = "succeeded"
        row.row_count = result["row_count"]
        row.columns = result["columns"]
        row.rows = result["rows"]
        row.duration_ms = result["duration_ms"]
    except HiveUnavailableError as exc:
        row.status = "failed"
        row.error_message = str(exc)
    except Exception as exc:
        row.status = "failed"
        row.error_message = f"Hive query failed: {exc}"
    row.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return _response(row)


@router.get("/queries", response_model=list[HiveQueryResponse])
async def history(db: Annotated[AsyncSession, Depends(get_db)], _: str = Depends(get_current_user)) -> list[HiveQueryResponse]:
    rows = (await db.scalars(select(HiveQueryHistory).order_by(HiveQueryHistory.created_at.desc()).limit(100))).all()
    return [_response(row) for row in rows]
