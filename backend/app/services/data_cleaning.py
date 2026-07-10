"""Value-level data cleaning, applied on top of the column-name
normalization in csv_ingestion.py.

Two things happen here, deliberately conservative:

1. Missing-value sentinels ("N/A", "null", "-", ...) are normalized to real
   NaN/NULL so aggregates (COUNT/AVG/GROUP BY) don't silently treat them as
   their own category. Object columns that are then overwhelmingly (>=95%
   of non-null values, with a minimum sample size so a tiny column can't
   hit that bar by chance) numeric or date-like get coerced to that type --
   cells that fail to parse become NaN, counted as missing, never dropped.
   This only runs on the pandas ingestion path (small/medium files); the
   native `read_csv_auto` path for large files relies on DuckDB's own type
   sniffing instead, same tradeoff already made for column-name cleaning.

2. Outliers are counted (IQR, 1.5x) per numeric column and reported -- never
   removed or altered. Silently discarding a real answer (e.g. the largest
   order) would undermine the tool's job of answering questions about the
   data as uploaded.

Both together are exposed as a `ColumnQuality` report per table, computed
once at ingest time via `compute_quality` (SQL against the already-loaded
DuckDB table, so it works the same for both the pandas and native paths) and
cached on the session -- never recomputed on the chat-query hot path.
"""

import re
from dataclasses import dataclass

import pandas as pd

MISSING_SENTINELS = frozenset(
    {"", "na", "n/a", "n\\a", "null", "none", "nan", "-", "--", "?", "unknown", "missing"}
)

_CURRENCY_CHARS = re.compile(r"[$,€£%\s]")
_NUMERIC_TYPE_RE = re.compile(
    r"^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|UHUGEINT|"
    r"FLOAT|DOUBLE|DECIMAL|REAL)",
    re.IGNORECASE,
)

MIN_SAMPLE_SIZE = 20
COERCE_THRESHOLD = 0.95


@dataclass
class ColumnQuality:
    missing_count: int
    missing_pct: float
    outlier_count: int | None = None
    coerced_from: str | None = None


def _normalize_missing(series: pd.Series) -> pd.Series:
    if series.dtype != object:
        return series
    lowered = series.astype(str).str.strip().str.lower()
    mask = series.notna() & lowered.isin(MISSING_SENTINELS)
    return series.mask(mask)


def _accept_if_confident(original: pd.Series, coerced: pd.Series) -> pd.Series | None:
    non_null = original.notna()
    sample_size = int(non_null.sum())
    if sample_size < MIN_SAMPLE_SIZE:
        return None
    success = int((coerced.notna() & non_null).sum())
    if success / sample_size >= COERCE_THRESHOLD:
        return coerced
    return None


def _try_coerce_numeric(series: pd.Series) -> pd.Series | None:
    stripped = series.astype(str).str.strip().str.replace(_CURRENCY_CHARS, "", regex=True)
    stripped = stripped.where(series.notna())
    coerced = pd.to_numeric(stripped, errors="coerce")
    return _accept_if_confident(series, coerced)


def _try_coerce_datetime(series: pd.Series) -> pd.Series | None:
    coerced = pd.to_datetime(series, errors="coerce", format="mixed")
    return _accept_if_confident(series, coerced)


def clean_values(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Normalize missing sentinels and coerce confidently-typed object
    columns. Returns the cleaned frame plus a {column: "string"} map of
    which columns were coerced from string, for the quality report."""
    df = df.copy()
    coerced_from: dict[str, str] = {}
    for col in df.columns:
        series = _normalize_missing(df[col])
        if series.dtype == object:
            numeric = _try_coerce_numeric(series)
            if numeric is not None:
                series = numeric
                coerced_from[col] = "string"
            else:
                dt = _try_coerce_datetime(series)
                if dt is not None:
                    series = dt
                    coerced_from[col] = "string"
        df[col] = series
    return df, coerced_from


def _is_numeric_type(duckdb_type: str) -> bool:
    return bool(_NUMERIC_TYPE_RE.match(duckdb_type.strip()))


def _missing_expr(column_name: str, duckdb_type: str) -> str:
    ident = f'"{column_name}"'
    if duckdb_type.strip().upper() != "VARCHAR":
        return f"{ident} IS NULL"
    sentinels = ", ".join(f"'{s}'" for s in MISSING_SENTINELS if s)
    return f"({ident} IS NULL OR trim({ident}) = '' OR lower(trim({ident})) IN ({sentinels}))"


def compute_quality(
    conn, table_name: str, columns: list, coerced_from: dict[str, str] | None = None
) -> dict[str, ColumnQuality]:
    """Compute a per-column quality report against an already-loaded DuckDB
    table. Works identically for tables loaded via pandas or via
    `read_csv_auto` -- missing-sentinel strings are detected here even on
    the native path, where they were never mutated in the underlying data
    (reporting-only there, consistent with that path skipping pandas-side
    cleaning for performance). Runs once at ingest time, not on the
    chat-query path."""
    coerced_from = coerced_from or {}
    if not columns:
        return {}

    total = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    report: dict[str, ColumnQuality] = {}
    for col in columns:
        missing = conn.execute(
            f'SELECT COUNT(*) FROM "{table_name}" WHERE {_missing_expr(col.name, col.type)}'
        ).fetchone()[0]

        outlier_count = None
        if _is_numeric_type(col.type) and total >= MIN_SAMPLE_SIZE:
            row = conn.execute(
                f"""
                WITH bounds AS (
                    SELECT
                        quantile_cont("{col.name}", 0.25) AS q1,
                        quantile_cont("{col.name}", 0.75) AS q3
                    FROM "{table_name}"
                )
                SELECT COUNT(*)
                FROM "{table_name}", bounds
                WHERE "{col.name}" < bounds.q1 - 1.5 * (bounds.q3 - bounds.q1)
                   OR "{col.name}" > bounds.q3 + 1.5 * (bounds.q3 - bounds.q1)
                """
            ).fetchone()
            outlier_count = row[0] if row else 0

        report[col.name] = ColumnQuality(
            missing_count=missing,
            missing_pct=round(missing / total, 4) if total else 0.0,
            outlier_count=outlier_count,
            coerced_from=coerced_from.get(col.name),
        )
    return report
