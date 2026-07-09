from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.services.session_manager import SessionManager


def test_create_session_returns_isolated_duckdb_connections():
    manager = SessionManager(ttl_minutes=30)
    a = manager.create_session()
    b = manager.create_session()

    assert a.session_id != b.session_id
    a.conn.execute("CREATE TABLE t AS SELECT 1 AS x")
    assert manager.get_session(a.session_id).conn.execute("SELECT * FROM t").fetchall() == [(1,)]
    with pytest.raises(Exception):
        b.conn.execute("SELECT * FROM t")


def test_get_session_updates_last_accessed():
    manager = SessionManager(ttl_minutes=30)
    record = manager.create_session()
    original = record.last_accessed_at
    record.last_accessed_at = original - timedelta(minutes=1)

    manager.get_session(record.session_id)
    assert record.last_accessed_at > original - timedelta(minutes=1)


def test_get_session_raises_404_for_unknown_id():
    manager = SessionManager(ttl_minutes=30)
    with pytest.raises(HTTPException) as exc_info:
        manager.get_session("does-not-exist")
    assert exc_info.value.status_code == 404


def test_expired_session_is_evicted_and_raises_404():
    manager = SessionManager(ttl_minutes=5)
    record = manager.create_session()
    record.last_accessed_at -= timedelta(minutes=6)

    with pytest.raises(HTTPException) as exc_info:
        manager.get_session(record.session_id)
    assert exc_info.value.status_code == 404
    # A second lookup still 404s rather than raising a KeyError - confirms eviction happened.
    with pytest.raises(HTTPException):
        manager.get_session(record.session_id)


def test_close_session_removes_it():
    manager = SessionManager(ttl_minutes=30)
    record = manager.create_session()
    manager.close_session(record.session_id)
    with pytest.raises(HTTPException) as exc_info:
        manager.get_session(record.session_id)
    assert exc_info.value.status_code == 404


def test_close_unknown_session_raises_404():
    manager = SessionManager(ttl_minutes=30)
    with pytest.raises(HTTPException) as exc_info:
        manager.close_session("does-not-exist")
    assert exc_info.value.status_code == 404
