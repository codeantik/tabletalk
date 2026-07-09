"""Phase 6 load test: measure CSV ingestion + query latency at scale.

Inflates the sample `order_items.csv` (20K rows) up to 1M/5M rows by tiling
real rows with fresh sequential IDs, then times two ingestion strategies
(pandas -> DuckDB, the current production path; and DuckDB's native
`read_csv_auto`) plus a representative aggregate query, at each scale.

Run from `backend/` with the project venv active:
    python scripts/perf_load_test.py [path/to/order_items.csv]

Not a pytest test -- this is a manual measurement tool whose numbers feed
the README's Phase 6 section. It intentionally bypasses the HTTP-level
MAX_UPLOAD_SIZE_MB gate (a separate, tunable config knob) so the mechanics
of ingestion itself can be measured at 1-5M rows.
"""

import io
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.csv_ingestion import _clean_columns  # noqa: E402

SCALES = [20_000, 1_000_000, 5_000_000]
QUERY = (
    'SELECT product_id, SUM(quantity * price_at_purchase) AS revenue '
    'FROM order_items GROUP BY product_id ORDER BY revenue DESC LIMIT 20'
)


def inflate(base: pd.DataFrame, n_rows: int) -> pd.DataFrame:
    reps = -(-n_rows // len(base))  # ceil division
    tiled = pd.concat([base] * reps, ignore_index=True).iloc[:n_rows].copy()
    tiled["order_item_id"] = range(1, len(tiled) + 1)
    return tiled


def time_pandas_path(df: pd.DataFrame) -> tuple[float, float]:
    """Mirrors csv_ingestion._ingest_dataframe: pandas parse (already done
    by caller) -> clean columns -> register -> CREATE TABLE AS SELECT."""
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode()

    t0 = time.perf_counter()
    parsed = pd.read_csv(io.BytesIO(csv_bytes))
    parsed = _clean_columns(parsed)
    parse_s = time.perf_counter() - t0

    conn = duckdb.connect(":memory:")
    t0 = time.perf_counter()
    conn.register("_incoming", parsed)
    conn.execute('CREATE OR REPLACE TABLE "order_items" AS SELECT * FROM _incoming')
    conn.unregister("_incoming")
    load_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    conn.execute(QUERY).fetchall()
    query_s = time.perf_counter() - t0
    conn.close()
    return parse_s + load_s, query_s


def time_native_path(df: pd.DataFrame) -> tuple[float, float]:
    """DuckDB's own read_csv_auto reading straight from a file path, with
    column normalization applied after load via ALTER TABLE RENAME COLUMN."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        df.to_csv(f, index=False)
        path = f.name

    conn = duckdb.connect(":memory:")
    t0 = time.perf_counter()
    conn.execute(
        f"CREATE OR REPLACE TABLE \"order_items\" AS SELECT * FROM read_csv_auto('{path}')"
    )
    raw_cols = [row[0] for row in conn.execute('DESCRIBE "order_items"').fetchall()]
    from app.services.csv_ingestion import dedupe_names, normalize_identifier

    normalized = dedupe_names([normalize_identifier(c, "column") for c in raw_cols])
    for old, new in zip(raw_cols, normalized):
        if old != new:
            conn.execute(f'ALTER TABLE "order_items" RENAME COLUMN "{old}" TO "{new}"')
    load_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    conn.execute(QUERY).fetchall()
    query_s = time.perf_counter() - t0
    conn.close()
    Path(path).unlink(missing_ok=True)
    return load_s, query_s


def _load_base_order_items(arg: str | None) -> pd.DataFrame:
    if arg:
        return pd.read_csv(arg)
    zip_path = Path(__file__).resolve().parent.parent.parent / "Online Shop 2024.zip"
    with zipfile.ZipFile(zip_path) as zf, zf.open("order_items.csv") as f:
        return pd.read_csv(f)


def main() -> None:
    base = _load_base_order_items(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"base rows: {len(base)}\n")
    print(f"{'rows':>10} | {'pandas ingest (s)':>18} | {'native ingest (s)':>18} | {'pandas query (s)':>17} | {'native query (s)':>17}")
    print("-" * 95)
    for n in SCALES:
        df = inflate(base, n)
        p_ingest, p_query = time_pandas_path(df)
        n_ingest, n_query = time_native_path(df)
        print(f"{n:>10} | {p_ingest:>18.3f} | {n_ingest:>18.3f} | {p_query:>17.3f} | {n_query:>17.3f}")


if __name__ == "__main__":
    main()
