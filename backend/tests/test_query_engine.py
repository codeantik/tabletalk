from datetime import datetime, timezone

import duckdb
import pytest
import sqlglot

from app.services.csv_ingestion import ingest_upload_batch
from app.services.query_engine import (
    QueryValidationError,
    apply_row_limit,
    execute_with_timeout,
    validate_select_sql,
)
from app.services.session_manager import SessionRecord


def make_session() -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        session_id="test-session",
        conn=duckdb.connect(database=":memory:"),
        created_at=now,
        last_accessed_at=now,
    )


def parse_select(sql: str):
    return sqlglot.parse_one(sql, dialect="duckdb")


def test_validate_select_sql_accepts_plain_select():
    stmt = validate_select_sql("SELECT * FROM orders", {"orders"})
    assert stmt.sql(dialect="duckdb") == "SELECT * FROM orders"


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES (1, 2)",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "UPDATE orders SET a = 1",
    ],
)
def test_validate_select_sql_rejects_non_select_statements(sql):
    with pytest.raises(QueryValidationError):
        validate_select_sql(sql, {"orders"})


def test_validate_select_sql_rejects_multiple_statements():
    with pytest.raises(QueryValidationError):
        validate_select_sql("SELECT * FROM orders; SELECT * FROM customers", {"orders", "customers"})


def test_validate_select_sql_rejects_unknown_table():
    with pytest.raises(QueryValidationError):
        validate_select_sql("SELECT * FROM secrets", {"orders"})


def test_validate_select_sql_accepts_table_defined_only_via_cte():
    stmt = validate_select_sql(
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent", {"orders"}
    )
    assert isinstance(stmt.sql(dialect="duckdb"), str)


def test_apply_row_limit_adds_limit_when_absent():
    stmt = parse_select("SELECT * FROM orders")
    limited, applied = apply_row_limit(stmt, 100)
    assert applied is True
    assert "LIMIT 100" in limited.sql(dialect="duckdb")


def test_apply_row_limit_caps_oversized_limit():
    stmt = parse_select("SELECT * FROM orders LIMIT 100000")
    limited, applied = apply_row_limit(stmt, 100)
    assert applied is True
    assert "LIMIT 100" in limited.sql(dialect="duckdb")


def test_apply_row_limit_leaves_in_bounds_limit_untouched():
    stmt = parse_select("SELECT * FROM orders LIMIT 10")
    limited, applied = apply_row_limit(stmt, 100)
    assert applied is False
    assert "LIMIT 10" in limited.sql(dialect="duckdb")


def test_execute_with_timeout_returns_columns_and_rows():
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n3,4\n")])

    columns, rows = execute_with_timeout(session.conn, 'SELECT * FROM "orders" ORDER BY a', 5)

    assert columns == ["a", "b"]
    assert rows == [[1, 2], [3, 4]]


def test_execute_with_timeout_raises_on_slow_query():
    session = make_session()

    with pytest.raises(TimeoutError):
        execute_with_timeout(session.conn, "SELECT count(*) FROM range(100000000)", 0)
