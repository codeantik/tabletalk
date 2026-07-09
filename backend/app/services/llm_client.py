"""OpenAI wrapper that turns a natural-language question into SQL.

Uses a forced tool call so the model's output is structured ({sql,
explanation, intent}) rather than free text that would need to be parsed
back out.
"""

import json

from openai import OpenAI

from app.core.config import Settings

_TOOL_NAME = "generate_sql_query"

# Fixed intent enum the response_composer maps to a response shape. Kept in
# sync with backend/app/services/response_composer.py's mapping table.
INTENTS = ["trend", "comparison", "single_value", "lookup", "distribution", "unsupported"]

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": _TOOL_NAME,
            "description": "Return the SQL query, a short explanation, and an intent classification that answers the user's question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": (
                            "A single DuckDB-dialect SELECT statement that answers the "
                            "question. Omit this (or leave empty) only when intent is "
                            "'unsupported'."
                        ),
                    },
                    "explanation": {
                        "type": "string",
                        "description": "One or two sentences describing what the query does, in plain language. If intent is 'unsupported', explain briefly why the question can't be answered from this data instead.",
                    },
                    "intent": {
                        "type": "string",
                        "enum": INTENTS,
                        "description": (
                            "trend: a metric over time. comparison: a metric compared "
                            "across categories. single_value: one scalar answer. "
                            "lookup: a free-form multi-row/multi-column result. "
                            "distribution: how a metric breaks down across a small set "
                            "of categories. unsupported: the question is unrelated to "
                            "the data, requires a write, or requires external knowledge."
                        ),
                    },
                },
                "required": ["explanation", "intent"],
            },
        },
    }
]

_SYSTEM_PROMPT = (
    "You translate a user's natural-language question into a single SQL query "
    "against the tables described below, and classify the question's intent. Rules:\n"
    "- Use DuckDB SQL dialect.\n"
    "- Only ever produce a single SELECT statement (CTEs via WITH are fine, "
    "but the overall statement must be read-only).\n"
    "- Never use INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, COPY, or any "
    "other statement that isn't a SELECT.\n"
    "- Only reference the tables and columns listed below; never invent one.\n"
    "- Classify intent as one of: trend, comparison, single_value, lookup, "
    "distribution, unsupported. If the question can't be answered from this "
    "data (unrelated to the tables, needs a write, or needs outside "
    "knowledge), set intent to 'unsupported' and skip the SQL.\n"
    "- Always call the generate_sql_query tool with your answer."
)


def _client(settings: Settings) -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def generate_sql(
    question: str,
    schema_context: str,
    settings: Settings,
    *,
    previous_sql: str | None = None,
    previous_error: str | None = None,
) -> tuple[str | None, str, str]:
    """Ask the LLM for {sql, explanation, intent}. Raises RuntimeError if the
    model doesn't return a well-formed tool call."""
    user_content = f"Tables available:\n{schema_context}\n\nQuestion: {question}"
    if previous_sql is not None and previous_error is not None:
        user_content += (
            f"\n\nYour previous attempt was invalid.\n"
            f"Previous SQL: {previous_sql}\n"
            f"Error: {previous_error}\n"
            f"Please correct it and try again."
        )

    response = _client(settings).chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        tools=_TOOLS,
        tool_choice={"type": "function", "function": {"name": _TOOL_NAME}},
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    if not tool_calls:
        raise RuntimeError("Model did not return a tool call")

    args = json.loads(tool_calls[0].function.arguments)
    sql = args.get("sql") or None
    return sql, args["explanation"], args["intent"]


# Cap how many result rows are sent to the summary call -- large results are
# already row-limited for the client, but a wide LIMIT (e.g. 5000) is still
# far more than a 1-3 sentence summary needs and would just burn tokens.
_SUMMARY_MAX_ROWS = 30

_SUMMARY_SYSTEM_PROMPT = (
    "You write a short natural-language summary of a SQL query result for a "
    "data analysis chat app. Rules:\n"
    "- 1 to 3 sentences, plain language, no SQL jargon.\n"
    "- Only state numbers/facts that appear in the provided result data; "
    "never invent or re-derive values.\n"
    "- If the result was truncated, do not claim it's the complete dataset."
)


def synthesize_summary(
    question: str,
    intent: str,
    columns: list[str],
    rows: list[list],
    settings: Settings,
) -> str:
    """Ask the LLM for a 1-3 sentence summary grounded in the executed
    query's actual result rows (not re-derived from raw table data)."""
    truncated = len(rows) > _SUMMARY_MAX_ROWS
    sample_rows = rows[:_SUMMARY_MAX_ROWS]
    result_text = json.dumps({"columns": columns, "rows": sample_rows})
    if truncated:
        result_text += f"\n(truncated: showing {_SUMMARY_MAX_ROWS} of {len(rows)} rows)"

    user_content = (
        f"Question: {question}\nIntent: {intent}\nResult:\n{result_text}"
    )

    response = _client(settings).chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    return (response.choices[0].message.content or "").strip()
