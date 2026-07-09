"""Phase 6: manual demonstration of the raw-DuckDB concurrency hazard.

NOT a pytest test -- deliberately runs two threads against a single,
unsynchronized DuckDB connection, which was observed to occasionally crash
the whole process with a Windows fatal exception (heap corruption,
0xc0000374), not just return a wrong answer. That's too dangerous to leave
in the automated suite (a crash there takes every other test down with it),
but it's the actual evidence behind SessionRecord.lock in session_manager.py
and query_engine.py/csv_ingestion.py's use of it.

Run from `backend/` with the project venv active:
    python scripts/duckdb_concurrency_hazard_demo.py

Expect either a wrong result printed for one thread, or the process crashing
outright -- both are the hazard. Re-run a few times if the first attempt
looks clean; it doesn't reproduce on every single run.
"""

import threading

import duckdb


def main() -> None:
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE t AS SELECT * FROM range(200000) AS r(i)")
    results: dict[str, list] = {}

    def run(name: str, sql: str) -> None:
        results[name] = conn.execute(sql).fetchall()

    threads = [
        threading.Thread(target=run, args=("low", "SELECT i FROM t WHERE i < 3 ORDER BY i")),
        threading.Thread(target=run, args=("high", "SELECT i FROM t WHERE i >= 199997 ORDER BY i")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("low  (expected [(0,), (1,), (2,)]):         ", results.get("low"))
    print("high (expected [(199997,), (199998,), (199999,)]):", results.get("high"))


if __name__ == "__main__":
    main()
