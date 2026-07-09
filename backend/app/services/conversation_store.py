"""Server-side, per-session conversation history.

Each turn stores the question plus the already-shaped answer (sql/intent/
text/chart/table) -- not a raw, unbounded DuckDB result set. Chart/table
payloads are already row-limited and shaped for the client (see
response_composer.py), so storing them here is still "light" relative to
the intermediate result the query actually produced; it's what lets a
session's history be replayed on page reload (Phase 5) without re-running
every query. Follow-up question resolution (llm_client.generate_sql's
`history` param) only reads the lightweight question/sql/intent fields from
these turns, to keep that prompt small.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.models.schemas import ChartResponse, TableResponse

if TYPE_CHECKING:
    from app.services.session_manager import SessionRecord


@dataclass
class ConversationTurn:
    question: str
    created_at: datetime
    sql: str | None = None
    intent: str | None = None
    text: str | None = None
    chart: ChartResponse | None = None
    table: TableResponse | None = None
    error: str | None = None
    row_limit_applied: bool = False


def append_turn(session: "SessionRecord", turn: ConversationTurn) -> None:
    session.turns.append(turn)


def recent_turns(session: "SessionRecord", n: int) -> list[ConversationTurn]:
    """The last `n` turns, oldest first -- the order the LLM prompt wants them in."""
    if n <= 0:
        return []
    return session.turns[-n:]
