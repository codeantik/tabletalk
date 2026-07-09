"""OpenAI wrapper that turns a natural-language question into SQL.

Uses a forced tool call so the model's output is structured ({sql,
explanation}) rather than free text that would need to be parsed back out.
"""

import json

from openai import OpenAI

from app.core.config import Settings

_TOOL_NAME = "generate_sql_query"

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": _TOOL_NAME,
            "description": "Return the SQL query and a short explanation that answers the user's question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A single DuckDB-dialect SELECT statement that answers the question.",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "One or two sentences describing what the query does, in plain language.",
                    },
                },
                "required": ["sql", "explanation"],
            },
        },
    }
]

_SYSTEM_PROMPT = (
    "You translate a user's natural-language question into a single SQL query "
    "against the tables described below. Rules:\n"
    "- Use DuckDB SQL dialect.\n"
    "- Only ever produce a single SELECT statement (CTEs via WITH are fine, "
    "but the overall statement must be read-only).\n"
    "- Never use INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, COPY, or any "
    "other statement that isn't a SELECT.\n"
    "- Only reference the tables and columns listed below; never invent one.\n"
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
) -> tuple[str, str]:
    """Ask the LLM for {sql, explanation}. Raises RuntimeError if the model
    doesn't return a well-formed tool call."""
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
    return args["sql"], args["explanation"]
