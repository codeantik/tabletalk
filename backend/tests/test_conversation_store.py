from datetime import datetime, timezone

import duckdb

from app.services.conversation_store import ConversationTurn, append_turn, recent_turns
from app.services.session_manager import SessionRecord


def make_session() -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        session_id="test-session",
        conn=duckdb.connect(database=":memory:"),
        created_at=now,
        last_accessed_at=now,
    )


def make_turn(question: str) -> ConversationTurn:
    return ConversationTurn(question=question, created_at=datetime.now(timezone.utc))


def test_append_turn_adds_to_session():
    session = make_session()
    append_turn(session, make_turn("q1"))
    assert [t.question for t in session.turns] == ["q1"]


def test_recent_turns_returns_last_n_oldest_first():
    session = make_session()
    for q in ["q1", "q2", "q3", "q4"]:
        append_turn(session, make_turn(q))

    assert [t.question for t in recent_turns(session, 2)] == ["q3", "q4"]


def test_recent_turns_returns_all_when_fewer_than_n():
    session = make_session()
    append_turn(session, make_turn("only"))

    assert [t.question for t in recent_turns(session, 3)] == ["only"]


def test_recent_turns_empty_session_returns_empty_list():
    session = make_session()
    assert recent_turns(session, 3) == []


def test_recent_turns_with_zero_returns_empty_list():
    session = make_session()
    append_turn(session, make_turn("q1"))
    assert recent_turns(session, 0) == []
