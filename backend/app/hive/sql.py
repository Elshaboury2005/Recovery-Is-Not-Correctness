"""Conservative read-only SQL validation for the Hive Explorer."""

from __future__ import annotations

import re


class HiveSqlValidationError(ValueError):
    """Raised when a query is not safe for the read-only explorer."""


_ALLOWED = {"select", "show", "describe", "desc", "explain"}


def validate_read_only_sql(sql: str) -> str:
    query = sql.strip()
    if not query:
        raise HiveSqlValidationError("SQL query cannot be empty")
    if len(query) > 50_000:
        raise HiveSqlValidationError("SQL query exceeds the 50,000 character limit")
    if ";" in query[:-1] or "--" in query or "/*" in query or "*/" in query:
        raise HiveSqlValidationError("Multiple statements and SQL comments are not allowed")
    keyword = re.match(r"^([A-Za-z]+)\b", query)
    if not keyword or keyword.group(1).lower() not in _ALLOWED:
        raise HiveSqlValidationError("Only SELECT, SHOW, DESCRIBE, and EXPLAIN statements are allowed")
    return query
