"""Validates and executes LLM-generated SQL against a session's DuckDB.

Untrusted SQL from the LLM only ever reaches DuckDB after sqlglot confirms
it is a single read-only SELECT that references tables already loaded into
the session -- that check is the only thing standing between a hallucinated
or malicious query and the rest of the session's data.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass

import duckdb
import sqlglot
from sqlglot import exp

from app.core.config import Settings
from app.models.schemas import ChartResponse, TableResponse
from app.services.csv_ingestion import list_tables
from app.services.llm_client import generate_sql, synthesize_summary
from app.services.response_composer import compose
from app.services.session_manager import SessionRecord

_DIALECT = "duckdb"


class QueryValidationError(Exception):
    """LLM-generated SQL failed the read-only/known-tables safety check."""


@dataclass
class QueryResult:
    sql: str | None = None
    intent: str | None = None
    text: str | None = None
    chart: ChartResponse | None = None
    table: TableResponse | None = None
    error: str | None = None
    row_limit_applied: bool = False


def build_schema_context(session: SessionRecord) -> str:
    lines = [
        f"- {table.name}: " + ", ".join(f"{c.name} ({c.type})" for c in table.columns)
        for table in list_tables(session)
    ]
    return "\n".join(lines) if lines else "(no tables loaded in this session)"


def validate_select_sql(sql: str, allowed_tables: set[str]) -> exp.Select:
    """Parse `sql` and reject anything but a single read-only SELECT over
    known tables. Returns the parsed statement so the caller can apply a
    row limit without re-parsing."""
    try:
        statements = [s for s in sqlglot.parse(sql, dialect=_DIALECT) if s is not None]
    except Exception as exc:
        raise QueryValidationError(f"Could not parse SQL: {exc}") from exc

    if len(statements) != 1:
        raise QueryValidationError("Only a single SQL statement is allowed")

    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise QueryValidationError("Only SELECT statements are allowed")

    cte_names = {cte.alias_or_name for cte in stmt.find_all(exp.CTE)}
    referenced_tables = {table.name for table in stmt.find_all(exp.Table)}
    unknown = referenced_tables - cte_names - allowed_tables
    if unknown:
        raise QueryValidationError(
            f"Query references unknown table(s): {', '.join(sorted(unknown))}"
        )
    return stmt


def apply_row_limit(stmt: exp.Select, max_rows: int) -> tuple[exp.Select, bool]:
    """Add a LIMIT if the query has none, or cap an oversized one. Returns
    the (possibly unchanged) statement and whether a cap was applied."""
    existing = stmt.args.get("limit")
    if existing is None:
        return stmt.limit(max_rows, copy=False), True
    try:
        current = int(existing.expression.this)
    except (AttributeError, TypeError, ValueError):
        return stmt, False
    if current > max_rows:
        return stmt.limit(max_rows, copy=False), True
    return stmt, False


def execute_with_timeout(
    conn: duckdb.DuckDBPyConnection, sql: str, timeout_seconds: int
) -> tuple[list[str], list[list]]:
    def _run() -> tuple[list[str], list[list]]:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
        return columns, rows

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            conn.interrupt()
            raise TimeoutError(f"Query did not complete within {timeout_seconds}s") from None


def _early_result(intent: str, sql: str | None, explanation: str) -> QueryResult | None:
    """Short-circuit before validation/execution when the model declined the
    question (intent='unsupported') or gave no SQL despite a supported
    intent. `explanation` doubles as the user-facing refusal message."""
    if intent == "unsupported":
        return QueryResult(intent=intent, error=explanation or "I can't answer that from this data.")
    if sql is None:
        return QueryResult(intent=intent, error="Model did not provide SQL for a supported intent.")
    return None


def run_nl_query(session: SessionRecord, settings: Settings, question: str) -> QueryResult:
    """Generate, validate (with one self-correcting retry), and execute SQL
    for `question`, then compose the result into a text/chart/table
    response. Never raises -- validation, execution, and unsupported-intent
    outcomes all come back as a QueryResult with `error` set."""
    allowed_tables = set(session.table_sources.keys())
    schema_context = build_schema_context(session)

    sql, explanation, intent = generate_sql(question, schema_context, settings)
    early = _early_result(intent, sql, explanation)
    if early is not None:
        return early

    try:
        stmt = validate_select_sql(sql, allowed_tables)
    except QueryValidationError as first_error:
        sql, explanation, intent = generate_sql(
            question,
            schema_context,
            settings,
            previous_sql=sql,
            previous_error=str(first_error),
        )
        early = _early_result(intent, sql, explanation)
        if early is not None:
            return early
        try:
            stmt = validate_select_sql(sql, allowed_tables)
        except QueryValidationError as second_error:
            return QueryResult(sql=sql, intent=intent, error=str(second_error))

    limited_stmt, row_limit_applied = apply_row_limit(stmt, settings.max_rows_returned)
    final_sql = limited_stmt.sql(dialect=_DIALECT)

    try:
        columns, rows = execute_with_timeout(
            session.conn, final_sql, settings.query_timeout_seconds
        )
    except Exception as exc:
        return QueryResult(sql=final_sql, intent=intent, error=f"Query execution failed: {exc}")

    composition = compose(intent, columns, rows)
    text = synthesize_summary(question, intent, columns, rows, settings)

    return QueryResult(
        sql=final_sql,
        intent=intent,
        text=text,
        chart=composition.chart,
        table=composition.table,
        row_limit_applied=row_limit_applied,
    )
