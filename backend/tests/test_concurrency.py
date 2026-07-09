"""Phase 6 concurrency checks.

A raw-DuckDB experiment (`backend/scripts/duckdb_concurrency_hazard_demo.py`,
see README > Phase 6) confirmed that two threads calling `.execute()` on the
*same* DuckDB connection concurrently, with no external synchronization, can
corrupt state badly enough to crash the process (a Windows fatal exception /
heap corruption was observed, not just a wrong result) -- deliberately
enough of a hazard that it is NOT reproduced here as a pytest test, since a
process-level crash would take the whole test run down with it, not just
this one test. FastAPI runs sync route handlers in a thread pool, so two
requests hitting the same session_id at once (a double-click, two open tabs)
would hit exactly this. `SessionRecord.lock` (session_manager.py) serializes
access to `conn`; the tests below exercise the app's actual code paths
(which always go through that lock) and confirm both same-session and
cross-session concurrent access come back correct.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import duckdb
import pytest

from app.core.config import Settings
from app.services.csv_ingestion import ingest_upload_batch
from app.services.query_engine import run_nl_query
from app.services.session_manager import SessionRecord


def make_session(session_id: str = "test-session") -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        session_id=session_id,
        conn=duckdb.connect(database=":memory:"),
        created_at=now,
        last_accessed_at=now,
    )


def _settings() -> Settings:
    return Settings(openai_api_key="unused-in-tests")


def test_concurrent_queries_on_same_session_return_correct_isolated_results(monkeypatch):
    session = make_session()
    ingest_upload_batch(session, [("orders.csv", b"a,b\n1,2\n3,4\n5,6\n7,8\n")])

    def fake_generate_sql(question, schema_context, settings, *, history=None, **kwargs):
        threshold = int(question.split()[-1])
        return f'SELECT * FROM "orders" WHERE a > {threshold} ORDER BY a', "explanation", "lookup"

    from app.services import query_engine

    monkeypatch.setattr(query_engine, "generate_sql", fake_generate_sql)
    monkeypatch.setattr(query_engine, "synthesize_summary", lambda *a, **k: "summary")

    questions = [f"rows above {t}" for t in (1, 3, 5)]
    with ThreadPoolExecutor(max_workers=len(questions)) as pool:
        results = list(pool.map(lambda q: run_nl_query(session, _settings(), q), questions))

    by_threshold = {int(q.split()[-1]): r for q, r in zip(questions, results)}
    assert by_threshold[1].table.rows == [[3, 4], [5, 6], [7, 8]]
    assert by_threshold[3].table.rows == [[5, 6], [7, 8]]
    assert by_threshold[5].table.rows == [[7, 8]]
    assert len(session.turns) == 3


def test_concurrent_sessions_do_not_leak_tables_across_each_other():
    """Two sessions, each with its own DuckDB connection, ingest and query
    different tables at the same time. Nothing here shares state except the
    test process itself -- if session isolation ever regressed (e.g. a
    shared/global connection), one of the queries below would either see the
    other session's table or fail to see its own."""
    sessions = {
        "alpha": make_session("alpha"),
        "beta": make_session("beta"),
    }

    def setup(session_id: str, filename: str, content: bytes) -> None:
        ingest_upload_batch(sessions[session_id], [(filename, content)])

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda args: setup(*args),
                [
                    ("alpha", "widgets.csv", b"id,name\n1,foo\n2,bar\n"),
                    ("beta", "gadgets.csv", b"id,name\n9,baz\n"),
                ],
            )
        )

    def query(session_id: str, table_name: str) -> list:
        from app.services.query_engine import execute_with_timeout

        with sessions[session_id].lock:
            _, rows = execute_with_timeout(
                sessions[session_id].conn, f'SELECT * FROM "{table_name}" ORDER BY id', 5
            )
        return rows

    with ThreadPoolExecutor(max_workers=2) as pool:
        alpha_future = pool.submit(query, "alpha", "widgets")
        beta_future = pool.submit(query, "beta", "gadgets")
        alpha_rows = alpha_future.result()
        beta_rows = beta_future.result()

    assert alpha_rows == [[1, "foo"], [2, "bar"]]
    assert beta_rows == [[9, "baz"]]
    assert "gadgets" not in sessions["alpha"].table_sources
    assert "widgets" not in sessions["beta"].table_sources
    with pytest.raises(Exception):
        sessions["alpha"].conn.execute('SELECT * FROM "gadgets"')
    with pytest.raises(Exception):
        sessions["beta"].conn.execute('SELECT * FROM "widgets"')
