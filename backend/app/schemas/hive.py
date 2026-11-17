"""API contracts for Hive health and read-only queries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HiveQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(..., min_length=1, max_length=50_000)
    max_rows: int = Field(default=500, ge=1, le=5_000)


class HiveQueryResponse(BaseModel):
    query_id: str
    sql: str
    status: str
    row_count: int | None
    columns: list[str] | None
    rows: list[list[Any]] | None
    duration_ms: float | None
    error_message: str | None


class HiveTableResponse(BaseModel):
    table_name: str
    columns: list[dict[str, Any]] | None = None
    error_message: str | None = None


class HiveColumnDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    hive_type: str = Field(..., min_length=1, max_length=128, pattern=r"^(?:BOOLEAN|TINYINT|SMALLINT|INT|BIGINT|FLOAT|DOUBLE|DECIMAL(?:\([0-9]{1,3},[0-9]{1,3}\))?|STRING|CHAR(?:\([0-9]{1,4}\))?|VARCHAR(?:\([0-9]{1,4}\))?|DATE|TIMESTAMP|BINARY|ARRAY<(?:BOOLEAN|TINYINT|SMALLINT|INT|BIGINT|FLOAT|DOUBLE|STRING|DATE|TIMESTAMP)>|MAP<(?:STRING|INT|BIGINT),(?:BOOLEAN|TINYINT|SMALLINT|INT|BIGINT|FLOAT|DOUBLE|STRING|DATE|TIMESTAMP)>)$")


class HiveTableRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_name: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    location: str = Field(..., min_length=12, max_length=2_000, pattern=r"^hdfs://[^\s;'\"]+$")
    columns: list[HiveColumnDefinition] = Field(..., min_length=1, max_length=256)
