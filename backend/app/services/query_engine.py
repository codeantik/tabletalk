"""Validates and executes LLM-generated SQL against a session's DuckDB.

Untrusted SQL from the LLM only ever reaches DuckDB after sqlglot confirms
it is a single read-only SELECT that references tables already loaded into
the session -- that check is the only thing standing between a hallucinated
or malicious query and the rest of the session's data.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone

import duckdb
import sqlglot
from sqlglot import exp

from app.core.config import Settings
from app.core.logging import get_logger, log_event
from app.models.schemas import ChartResponse, TableResponse
from app.services.conversation_store import ConversationTurn, append_turn, recent_turns
from app.services.csv_ingestion import list_tables
from app.services.llm_client import LLMServiceError, generate_sql, synthesize_summary
from app.services.response_composer import compose
from app.services.session_manager import SessionRecord

_DIALECT = "duckdb"
_logger = get_logger(__name__)


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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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


def _fallback_summary(rows: list[list]) -> str:
    """Deterministic caption used when the NL-summary LLM call itself fails
    (LLMServiceError) after the SQL already executed successfully -- the
    query result is real and worth returning even if we can't narrate it,
    and a chart response must never ship without some caption."""
    if not rows:
        return "The query returned no results."
    return f"The query returned {len(rows)} row(s). (AI summary is temporarily unavailable.)"


def _generate_sql_logged(
    question: str,
    schema_context: str,
    settings: Settings,
    *,
    history: list[ConversationTurn],
    start: float,
    previous_sql: str | None = None,
    previous_error: str | None = None,
) -> tuple[str | None, str, str]:
    """Wraps llm_client.generate_sql to log+re-raise LLMServiceError (a total
    LLM outage) before it propagates out of run_nl_query -- these calls never
    produce a QueryResult/stored turn, but they should still show up in the
    query log for observability."""
    try:
        return generate_sql(
            question,
            schema_context,
            settings,
            history=history,
            previous_sql=previous_sql,
            previous_error=previous_error,
        )
    except LLMServiceError as exc:
        log_event(
            _logger,
            "query_turn",
            question=question,
            sql=None,
            intent=None,
            validation="not_attempted",
            execution="not_attempted",
            error=str(exc),
            latency_ms=round((time.monotonic() - start) * 1000, 1),
        )
        raise


def run_nl_query(session: SessionRecord, settings: Settings, question: str) -> QueryResult:
    """Generate, validate (with one self-correcting retry), and execute SQL
    for `question`, then compose the result into a text/chart/table
    response. Every graceful failure (unsupported intent, validation
    failure, execution timeout, malformed model output) comes back as a
    QueryResult with `error` set and is recorded in the session's
    conversation history; an LLMServiceError (the LLM API itself is down)
    propagates to the caller uncaught, since there's no answer -- graceful
    or otherwise -- to store or return."""
    start = time.monotonic()
    allowed_tables = set(session.table_sources.keys())
    schema_context = build_schema_context(session)
    history = recent_turns(session, settings.history_turns_context)

    def _finish(result: QueryResult, *, validation: str, execution: str) -> QueryResult:
        log_event(
            _logger,
            "query_turn",
            question=question,
            sql=result.sql,
            intent=result.intent,
            validation=validation,
            execution=execution,
            error=result.error,
            latency_ms=round((time.monotonic() - start) * 1000, 1),
        )
        append_turn(
            session,
            ConversationTurn(
                question=question,
                created_at=result.created_at,
                sql=result.sql,
                intent=result.intent,
                text=result.text,
                chart=result.chart,
                table=result.table,
                error=result.error,
                row_limit_applied=result.row_limit_applied,
            ),
        )
        return result

    try:
        sql, explanation, intent = _generate_sql_logged(
            question, schema_context, settings, history=history, start=start
        )
    except RuntimeError as exc:
        return _finish(
            QueryResult(error=f"Could not generate a query for that question: {exc}"),
            validation="not_attempted",
            execution="not_attempted",
        )

    early = _early_result(intent, sql, explanation)
    if early is not None:
        return _finish(early, validation="skipped_unsupported", execution="skipped_unsupported")

    try:
        stmt = validate_select_sql(sql, allowed_tables)
        validation_result = "passed"
    except QueryValidationError as first_error:
        try:
            sql, explanation, intent = _generate_sql_logged(
                question,
                schema_context,
                settings,
                history=history,
                start=start,
                previous_sql=sql,
                previous_error=str(first_error),
            )
        except RuntimeError as exc:
            return _finish(
                QueryResult(sql=sql, intent=intent, error=f"Could not correct the query: {exc}"),
                validation="failed_retry_malformed",
                execution="not_attempted",
            )
        early = _early_result(intent, sql, explanation)
        if early is not None:
            return _finish(early, validation="retry_unsupported", execution="skipped_unsupported")
        try:
            stmt = validate_select_sql(sql, allowed_tables)
            validation_result = "passed_after_retry"
        except QueryValidationError as second_error:
            return _finish(
                QueryResult(sql=sql, intent=intent, error=str(second_error)),
                validation="failed_twice",
                execution="not_attempted",
            )

    limited_stmt, row_limit_applied = apply_row_limit(stmt, settings.max_rows_returned)
    final_sql = limited_stmt.sql(dialect=_DIALECT)

    try:
        columns, rows = execute_with_timeout(
            session.conn, final_sql, settings.query_timeout_seconds
        )
    except Exception as exc:
        return _finish(
            QueryResult(sql=final_sql, intent=intent, error=f"Query execution failed: {exc}"),
            validation=validation_result,
            execution="failed",
        )

    composition = compose(intent, columns, rows)
    try:
        text = synthesize_summary(question, intent, columns, rows, settings)
    except LLMServiceError as exc:
        log_event(_logger, "summary_fallback", question=question, error=str(exc))
        text = _fallback_summary(rows)

    return _finish(
        QueryResult(
            sql=final_sql,
            intent=intent,
            text=text,
            chart=composition.chart,
            table=composition.table,
            row_limit_applied=row_limit_applied,
        ),
        validation=validation_result,
        execution="succeeded",
    )
