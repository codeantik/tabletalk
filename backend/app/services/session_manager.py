"""In-memory, session-scoped DuckDB connections with idle-TTL eviction.

Each session owns its own DuckDB connection so uploaded tables from one
session are never visible to another. Eviction is lazy: expired sessions are
swept out on the next manager call rather than via a background timer, which
is sufficient for a PoC's request-driven lifecycle.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import duckdb
from fastapi import HTTPException, status

from app.services.conversation_store import ConversationTurn


@dataclass
class SessionRecord:
    session_id: str
    conn: duckdb.DuckDBPyConnection
    created_at: datetime
    last_accessed_at: datetime
    table_sources: dict[str, str] = field(default_factory=dict)
    turns: list[ConversationTurn] = field(default_factory=list)
    # A single DuckDB connection is not safe for concurrent use from
    # multiple threads (confirmed empirically in Phase 6: concurrent
    # `execute()` calls on the same connection silently returned wrong
    # results, no exception raised). FastAPI runs sync route handlers in a
    # thread pool, so two requests hitting the same session_id at once (a
    # double-click, two open tabs) would otherwise race on `conn`. Every
    # direct use of `conn` (ingestion, schema introspection, query
    # execution) takes this lock first -- see csv_ingestion.py and
    # query_engine.py.
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionManager:
    def __init__(self, ttl_minutes: int):
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, SessionRecord] = {}

    def _is_expired(self, record: SessionRecord, now: datetime) -> bool:
        return now - record.last_accessed_at > self._ttl

    def _sweep_expired(self, now: datetime) -> None:
        expired_ids = [
            session_id
            for session_id, record in self._sessions.items()
            if self._is_expired(record, now)
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id).conn.close()

    def create_session(self) -> SessionRecord:
        now = datetime.now(timezone.utc)
        self._sweep_expired(now)
        session_id = str(uuid.uuid4())
        record = SessionRecord(
            session_id=session_id,
            conn=duckdb.connect(database=":memory:"),
            created_at=now,
            last_accessed_at=now,
        )
        self._sessions[session_id] = record
        return record

    def get_session(self, session_id: str) -> SessionRecord:
        now = datetime.now(timezone.utc)
        self._sweep_expired(now)
        record = self._sessions.get(session_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or expired",
            )
        record.last_accessed_at = now
        return record

    def close_session(self, session_id: str) -> None:
        record = self._sessions.pop(session_id, None)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or expired",
            )
        record.conn.close()

    def expires_at(self, record: SessionRecord) -> datetime:
        return record.last_accessed_at + self._ttl


_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        from app.core.config import get_settings

        _manager = SessionManager(ttl_minutes=get_settings().session_ttl_minutes)
    return _manager
