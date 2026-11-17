from __future__ import annotations

import pytest

from app.hive.sql import HiveSqlValidationError, validate_read_only_sql
from app.services import hive_service


def test_read_only_sql_allows_inspection_statements() -> None:
    assert validate_read_only_sql("SHOW TABLES;") == "SHOW TABLES;"
    assert validate_read_only_sql("select * from sales") == "select * from sales"


@pytest.mark.parametrize("sql", ["DROP TABLE sales", "INSERT INTO sales VALUES (1)", "SELECT 1; DROP TABLE sales", "-- comment\nSELECT 1"])
def test_read_only_sql_rejects_mutation_or_multiple_statements(sql: str) -> None:
    with pytest.raises(HiveSqlValidationError):
        validate_read_only_sql(sql)


def test_hive_routes_require_authentication() -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    assert TestClient(app).get("/api/hive/health").status_code == 401
    assert TestClient(app).get("/api/hive/tables").status_code == 401
    assert TestClient(app).get("/api/hive/tables/sales").status_code == 401
    assert TestClient(app).post("/api/hive/tables", json={}).status_code == 401


def test_external_table_registration_rejects_non_hdfs_locations() -> None:
    with pytest.raises(ValueError, match="HDFS URI"):
        hive_service.register_external_parquet_table(
            "sales",
            "/local/path",
            [{"name": "id", "hive_type": "BIGINT"}],
        )


def test_external_table_registration_uses_bounded_parquet_ddl(monkeypatch: pytest.MonkeyPatch) -> None:
    class Cursor:
        statement = ""

        def execute(self, statement: str) -> None:
            self.statement = statement

        def close(self) -> None:
            pass

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self) -> Cursor:
            return self.cursor_instance

        def commit(self) -> None:
            pass

        def close(self) -> None:
            pass

    connection = Connection()
    monkeypatch.setattr(hive_service, "_connect", lambda: connection)
    result = hive_service.register_external_parquet_table(
        "sales",
        "hdfs://namenode:9000/data/sales",
        [{"name": "id", "hive_type": "BIGINT"}, {"name": "value", "hive_type": "STRING"}],
    )
    assert result["table_name"] == "sales"
    assert connection.cursor_instance.statement == (
        "CREATE EXTERNAL TABLE IF NOT EXISTS sales (id BIGINT, value STRING) "
        "STORED AS PARQUET LOCATION 'hdfs://namenode:9000/data/sales'"
    )
