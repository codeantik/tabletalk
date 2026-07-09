"""Deterministic mapping from (intent, result shape) -> response type.

This is invariant 5 from prompt.md: the backend decides text vs. chart vs.
table in code, not from the LLM's free-text output. `intent` comes from the
same LLM call that produced the SQL (see llm_client.generate_sql); the
mapping below combines it with the *actual* shape of the executed result
(row count, column count, per-column value kind) so a mismatched or
low-confidence intent still degrades gracefully to a table instead of
producing a nonsensical chart.

Mapping table:

    result shape                                    | intent              | response type
    -------------------------------------------------+---------------------+---------------
    1 row x 1 col (or 0 rows)                        | any                 | text
    1 date/datetime col + >=1 numeric col, >1 row     | trend               | chart:line
    1 category col + 1 numeric col, 2..PIE_MAX rows   | distribution        | chart:pie
    1 category col + >=1 numeric col, >1 row          | comparison/         | chart:bar
                                                       | distribution        |
    anything else                                     | lookup / fallback   | table

A chart response always also gets a `text` caption from the post-execution
summary call (query_engine.py) -- charts are never returned without a
caption ("mix" is the default, per prompt.md, not an either/or).
"""

import decimal
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from app.models.schemas import ChartDataPoint, ChartResponse, ChartSeriesPoint, TableResponse

# Above this many categories a bar chart stops being readable; fall back to
# a table instead of rendering an unreadable wall of bars.
BAR_MAX_CATEGORIES = 50
# Pie charts are used "sparingly" (prompt.md) -- only for a small, genuinely
# part-of-a-whole distribution.
PIE_MAX_CATEGORIES = 6


class ResponseType(str, Enum):
    TEXT = "text"
    LINE = "chart:line"
    BAR = "chart:bar"
    PIE = "chart:pie"
    TABLE = "table"


@dataclass
class Composition:
    response_type: ResponseType
    chart: ChartResponse | None = None
    table: TableResponse | None = None


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float, decimal.Decimal)) and not isinstance(value, bool)


def _is_datelike(value: object) -> bool:
    return isinstance(value, (date, datetime))


def _column_kinds(columns: list[str], rows: list[list]) -> list[str]:
    """Classify each column as 'numeric', 'date', or 'category' from the
    first non-null value in that column (query results are homogeneous per
    column, so one sample is enough)."""
    kinds = []
    for i in range(len(columns)):
        kind = "category"
        for row in rows:
            value = row[i]
            if value is None:
                continue
            if _is_datelike(value):
                kind = "date"
            elif _is_numeric(value):
                kind = "numeric"
            else:
                kind = "category"
            break
        kinds.append(kind)
    return kinds


def compose(intent: str, columns: list[str], rows: list[list]) -> Composition:
    """Decide response shape for a successful query result. Never raises --
    anything that doesn't fit a chart pattern falls back to `table`."""
    n_rows = len(rows)
    n_cols = len(columns)

    if n_rows == 0 or (n_rows == 1 and n_cols == 1):
        return Composition(response_type=ResponseType.TEXT)

    kinds = _column_kinds(columns, rows)
    numeric_idx = [i for i, k in enumerate(kinds) if k == "numeric"]
    date_idx = [i for i, k in enumerate(kinds) if k == "date"]
    category_idx = [i for i, k in enumerate(kinds) if k == "category"]

    if intent == "trend" and len(date_idx) == 1 and numeric_idx and n_rows > 1:
        return Composition(
            response_type=ResponseType.LINE,
            chart=_shape_chart("chart:line", columns, rows, date_idx[0], numeric_idx),
        )

    if (
        intent in ("comparison", "distribution")
        and len(category_idx) == 1
        and numeric_idx
        and 1 < n_rows <= BAR_MAX_CATEGORIES
    ):
        if intent == "distribution" and len(numeric_idx) == 1 and n_rows <= PIE_MAX_CATEGORIES:
            return Composition(
                response_type=ResponseType.PIE,
                chart=_shape_chart("chart:pie", columns, rows, category_idx[0], numeric_idx),
            )
        return Composition(
            response_type=ResponseType.BAR,
            chart=_shape_chart("chart:bar", columns, rows, category_idx[0], numeric_idx),
        )

    return Composition(
        response_type=ResponseType.TABLE,
        table=TableResponse(columns=columns, rows=rows),
    )


def _shape_chart(
    chart_type: str,
    columns: list[str],
    rows: list[list],
    x_idx: int,
    series_idx: list[int],
) -> ChartResponse:
    data = [
        ChartDataPoint(
            x=str(row[x_idx]),
            series=[
                ChartSeriesPoint(name=columns[i], value=float(row[i]))
                for i in series_idx
                if row[i] is not None
            ],
        )
        for row in rows
    ]
    return ChartResponse(type=chart_type, data=data)
