"""Phase 6 edge-case checklist (see prompt.md Phase 6, task 4).

Each test below documents pass/fail + handling for one scenario the phase
calls out explicitly. See README > Phase 6 for the human-readable checklist
these back.
"""

from datetime import datetime, timezone

import duckdb

from app.core.config import Settings
from app.services import query_engine
from app.services.csv_ingestion import ingest_upload_batch
from app.services.query_engine import run_nl_query
from app.services.session_manager import SessionRecord


def make_session() -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        session_id="test-session",
        conn=duckdb.connect(database=":memory:"),
        created_at=now,
        last_accessed_at=now,
    )


def _settings() -> Settings:
    return Settings(openai_api_key="unused-in-tests")


def test_empty_result_set_returns_text_not_chart_or_table(monkeypatch):
    """A query that legitimately matches nothing should surface as a plain
    text response ('no results'), not an empty/broken chart or table."""
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n3,4\n")])
    monkeypatch.setattr(
        query_engine,
        "generate_sql",
        lambda *a, **k: ('SELECT * FROM "orders" WHERE a > 999', "explanation", "lookup"),
    )
    monkeypatch.setattr(query_engine, "synthesize_summary", lambda *a, **k: "No matching rows.")

    result = run_nl_query(session, _settings(), "orders with a over 999")

    assert result.error is None
    assert result.chart is None
    assert result.table is None
    assert result.text == "No matching rows."


def test_nonexistent_column_reference_fails_gracefully_at_execution(monkeypatch):
    """sqlglot validation only checks table names, not columns (DuckDB owns
    column resolution) -- a hallucinated column on a real table passes
    validation and fails at execution, which run_nl_query catches and turns
    into a chat-level error rather than a 500."""
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n")])
    monkeypatch.setattr(
        query_engine,
        "generate_sql",
        lambda *a, **k: ('SELECT nonexistent_col FROM "orders"', "explanation", "lookup"),
    )

    result = run_nl_query(session, _settings(), "show me nonexistent_col")

    assert result.error is not None
    assert "Query execution failed" in result.error
    assert len(session.turns) == 1


def test_ambiguous_question_still_gets_a_best_guess_response_not_a_crash(monkeypatch):
    """No clarification-loop UX exists (documented limitation, README): an
    ambiguous question just gets the model's best-guess SQL/intent like any
    other question, and that still has to resolve to a valid response."""
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n3,4\n")])
    monkeypatch.setattr(
        query_engine,
        "generate_sql",
        lambda *a, **k: ('SELECT * FROM "orders" ORDER BY a', "Best guess: showing all orders.", "lookup"),
    )
    monkeypatch.setattr(query_engine, "synthesize_summary", lambda *a, **k: "Here are the orders.")

    result = run_nl_query(session, _settings(), "how are we doing?")

    assert result.error is None
    assert result.table is not None


def test_non_english_question_round_trips_without_error(monkeypatch):
    """Nothing in the pipeline assumes ASCII/English -- the question is an
    opaque string forwarded to the LLM and stored as-is."""
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n3,4\n")])
    seen_questions = []

    def fake_generate_sql(question, schema_context, settings, **kwargs):
        seen_questions.append(question)
        return 'SELECT * FROM "orders" ORDER BY a', "explanation", "lookup"

    monkeypatch.setattr(query_engine, "generate_sql", fake_generate_sql)
    monkeypatch.setattr(query_engine, "synthesize_summary", lambda *a, **k: "订单总数为 2。")

    question = "总共有多少订单？"
    result = run_nl_query(session, _settings(), question)

    assert result.error is None
    assert result.text == "订单总数为 2。"
    assert seen_questions == [question]
    assert session.turns[0].question == question


def test_extremely_broad_question_is_still_row_limited(monkeypatch):
    """'Tell me everything about the data' naturally produces a wide,
    unfiltered SELECT -- apply_row_limit must still cap it rather than
    return an unbounded result."""
    session = make_session()
    rows = "\n".join(f"{i},{i * 2}" for i in range(1, 21))
    ingest_upload_batch(session, [("orders.csv", f"a,b\n{rows}\n".encode())])
    monkeypatch.setattr(
        query_engine,
        "generate_sql",
        lambda *a, **k: ('SELECT * FROM "orders"', "explanation", "lookup"),
    )
    monkeypatch.setattr(query_engine, "synthesize_summary", lambda *a, **k: "summary")

    result = run_nl_query(session, Settings(openai_api_key="unused", max_rows_returned=5), "tell me everything about the data")

    assert result.error is None
    assert result.row_limit_applied is True
    assert len(result.table.rows) == 5


def test_sentiment_analysis_request_declines_as_unsupported_not_a_sql_hack(monkeypatch):
    """Sentiment analysis on free-text columns is outside SQL's reach and is
    explicitly out-of-scope for this PoC (prompt.md Phase 6, task 4) --
    the model is instructed to set intent='unsupported' for anything needing
    capabilities beyond SQL rather than faking it with a LIKE/keyword hack,
    and run_nl_query short-circuits before generating/executing any SQL."""
    session = make_session()
    ingest_upload_batch(session, [("reviews.csv", b"id,review_text\n1,great product\n")])
    monkeypatch.setattr(
        query_engine,
        "generate_sql",
        lambda *a, **k: (
            None,
            "Sentiment analysis requires natural-language understanding beyond SQL aggregation.",
            "unsupported",
        ),
    )

    result = run_nl_query(session, _settings(), "what's the overall sentiment of the reviews?")

    assert result.sql is None
    assert result.chart is None
    assert result.table is None
    assert "Sentiment analysis" in result.error
