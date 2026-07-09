from datetime import datetime, timezone

import duckdb
import pytest
import sqlglot

from app.core.config import Settings
from app.services import query_engine
from app.services.conversation_store import ConversationTurn, append_turn
from app.services.csv_ingestion import ingest_upload_batch
from app.services.llm_client import LLMServiceError
from app.services.query_engine import (
    QueryValidationError,
    apply_row_limit,
    execute_with_timeout,
    run_nl_query,
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


def _settings() -> Settings:
    return Settings(openai_api_key="unused-in-tests")


def test_run_nl_query_passes_recent_turns_as_history(monkeypatch):
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n3,4\n")])
    append_turn(
        session,
        ConversationTurn(
            question="prior question", created_at=datetime.now(timezone.utc), sql="SELECT 1", intent="lookup"
        ),
    )
    seen = {}

    def fake_generate_sql(question, schema_context, settings, *, history=None, **kwargs):
        seen["history"] = history
        return 'SELECT * FROM "orders" ORDER BY a', "explanation", "lookup"

    monkeypatch.setattr(query_engine, "generate_sql", fake_generate_sql)
    monkeypatch.setattr(query_engine, "synthesize_summary", lambda *args, **kwargs: "summary")

    run_nl_query(session, _settings(), "follow-up question")

    assert [t.question for t in seen["history"]] == ["prior question"]
    assert [t.question for t in session.turns] == ["prior question", "follow-up question"]


def test_run_nl_query_propagates_llm_service_error_without_storing_turn(monkeypatch):
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n")])

    def raise_llm_error(*args, **kwargs):
        raise LLMServiceError("outage")

    monkeypatch.setattr(query_engine, "generate_sql", raise_llm_error)

    with pytest.raises(LLMServiceError):
        run_nl_query(session, _settings(), "any question")

    assert session.turns == []


def test_run_nl_query_handles_malformed_model_response_gracefully(monkeypatch):
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n")])

    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError("model returned no tool call")

    monkeypatch.setattr(query_engine, "generate_sql", raise_runtime_error)

    result = run_nl_query(session, _settings(), "any question")

    assert result.error is not None
    assert "model returned no tool call" in result.error
    assert len(session.turns) == 1


def test_run_nl_query_falls_back_to_deterministic_summary_on_llm_outage(monkeypatch):
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n3,4\n")])
    monkeypatch.setattr(
        query_engine,
        "generate_sql",
        lambda *args, **kwargs: ('SELECT * FROM "orders" ORDER BY a', "explanation", "lookup"),
    )

    def raise_llm_error(*args, **kwargs):
        raise LLMServiceError("summary outage")

    monkeypatch.setattr(query_engine, "synthesize_summary", raise_llm_error)

    result = run_nl_query(session, _settings(), "show me the orders")

    assert result.error is None
    assert result.text is not None and "row(s)" in result.text
    assert result.table.rows == [[1, 2], [3, 4]]
