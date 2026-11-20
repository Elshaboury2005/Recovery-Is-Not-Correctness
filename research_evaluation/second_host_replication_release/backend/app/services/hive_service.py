"""Optional HiveServer2 query service with explicit unavailable behavior."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.core.config import get_settings


class HiveUnavailableError(RuntimeError):
    """Raised when HiveServer2 or its client driver is unavailable."""


_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HDFS_LOCATION = re.compile(r"^hdfs://[^\s;'\"]+$")
_HIVE_TYPE = re.compile(r"^(?:BOOLEAN|TINYINT|SMALLINT|INT|BIGINT|FLOAT|DOUBLE|DECIMAL(?:\([0-9]{1,3},[0-9]{1,3}\))?|STRING|CHAR(?:\([0-9]{1,4}\))?|VARCHAR(?:\([0-9]{1,4}\))?|DATE|TIMESTAMP|BINARY|ARRAY<(?:BOOLEAN|TINYINT|SMALLINT|INT|BIGINT|FLOAT|DOUBLE|STRING|DATE|TIMESTAMP)>|MAP<(?:STRING|INT|BIGINT),(?:BOOLEAN|TINYINT|SMALLINT|INT|BIGINT|FLOAT|DOUBLE|STRING|DATE|TIMESTAMP)>)$")


def _connect():
    settings = get_settings()
    try:
        from pyhive import hive
    except ImportError as exc:
        raise HiveUnavailableError("Hive client driver is not installed in the backend image") from exc
    try:
        return hive.connect(host=settings.HIVE_SERVER_HOST, port=settings.HIVE_SERVER_PORT, username=settings.HIVE_USERNAME, auth="NONE")
    except Exception as exc:
        raise HiveUnavailableError(f"HiveServer2 is unavailable: {exc}") from exc


def execute_read_only(sql: str, *, max_rows: int = 500) -> dict[str, Any]:
    started = time.perf_counter()
    connection = _connect()
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        raw_columns = cursor.description or []
        columns = [item[0] for item in raw_columns]
        rows = [list(row) for row in cursor.fetchmany(max_rows)]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": len(rows) >= max_rows, "duration_ms": round((time.perf_counter() - started) * 1000, 3)}
    finally:
        try:
            cursor.close()
        finally:
            connection.close()


def list_tables() -> list[str]:
    """Return table names through Hive's read-only metadata command."""
    result = execute_read_only("SHOW TABLES", max_rows=5_000)
    tables: list[str] = []
    for row in result["rows"]:
        if row:
            tables.append(str(row[-1]))
    return tables


def describe_table(table_name: str) -> list[dict[str, Any]]:
    """Return schema rows for a validated Hive identifier."""
    if not _TABLE_NAME.fullmatch(table_name):
        raise ValueError("Invalid Hive table identifier")
    result = execute_read_only(f"DESCRIBE {table_name}", max_rows=5_000)
    columns = result.get("columns") or []
    return [
        {str(columns[index] if index < len(columns) else "column"): value for index, value in enumerate(row)}
        for row in result.get("rows", [])
    ]


def register_external_parquet_table(table_name: str, location: str, columns: list[dict[str, str]]) -> dict[str, Any]:
    """Register an existing HDFS Parquet directory using a bounded DDL path.

    Arbitrary DDL is deliberately not exposed through the SQL Explorer. This
    narrow boundary validates every identifier/type/location before issuing a
    single idempotent CREATE EXTERNAL TABLE statement.
    """
    if not _TABLE_NAME.fullmatch(table_name):
        raise ValueError("Invalid Hive table identifier")
    if not _HDFS_LOCATION.fullmatch(location):
        raise ValueError("Table location must be an HDFS URI without quotes or statement separators")
    if not columns:
        raise ValueError("At least one table column is required")
    definitions: list[str] = []
    for column in columns:
        name = str(column.get("name", ""))
        hive_type = str(column.get("hive_type", ""))
        if not _TABLE_NAME.fullmatch(name):
            raise ValueError(f"Invalid Hive column identifier: {name}")
        if not _HIVE_TYPE.fullmatch(hive_type):
            raise ValueError(f"Invalid Hive column type: {hive_type}")
        definitions.append(f"{name} {hive_type}")
    sql = (
        f"CREATE EXTERNAL TABLE IF NOT EXISTS {table_name} ({', '.join(definitions)}) "
        f"STORED AS PARQUET LOCATION '{location}'"
    )
    started = time.perf_counter()
    connection = _connect()
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        try:
            connection.commit()
        except Exception:
            # HiveServer2 commonly commits DDL implicitly; retain compatibility
            # with drivers that do not expose a transaction commit operation.
            pass
    finally:
        try:
            cursor.close()
        finally:
            connection.close()
    return {"table_name": table_name, "location": location, "duration_ms": round((time.perf_counter() - started) * 1000, 3)}


async def hive_health() -> dict[str, Any]:
    def probe() -> dict[str, Any]:
        started = time.perf_counter()
        try:
            connection = _connect()
            connection.close()
            return {"connected": True, "status": "READY", "duration_ms": round((time.perf_counter() - started) * 1000, 3), "error": None}
        except HiveUnavailableError as exc:
            return {"connected": False, "status": "UNAVAILABLE", "duration_ms": round((time.perf_counter() - started) * 1000, 3), "error": str(exc)}
    return await asyncio.to_thread(probe)
