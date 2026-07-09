from datetime import datetime, timezone

import duckdb
import pytest
from fastapi import HTTPException

from app.services.csv_ingestion import (
    dedupe_names,
    ingest_upload_batch,
    list_tables,
    normalize_identifier,
)
from app.services.session_manager import SessionRecord


def make_session() -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        session_id="test-session",
        conn=duckdb.connect(database=":memory:"),
        created_at=now,
        last_accessed_at=now,
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Customer Name", "customer_name"),
        ("  Total $  ", "total"),
        ("already_clean", "already_clean"),
        ("Col--With---Dashes", "col_with_dashes"),
        ("", "column"),
        ("   ", "column"),
        ("2023_revenue", "column_2023_revenue"),
    ],
)
def test_normalize_identifier(raw, expected):
    assert normalize_identifier(raw, "column") == expected


def test_dedupe_names_suffixes_collisions_in_order():
    assert dedupe_names(["a", "a", "a", "b"]) == ["a", "a_2", "a_3", "b"]


def test_dedupe_names_avoids_colliding_with_pre_existing_suffixed_name():
    assert dedupe_names(["a_2", "a", "a"]) == ["a_2", "a", "a_3"]


def test_ingest_valid_csv_creates_table_with_normalized_columns():
    session = make_session()
    content = b"Customer Name,Total $\nAlice,10\nBob,20\n"

    tables = ingest_upload_batch(session, [("Sales Data.csv", content)])

    assert len(tables) == 1
    table = tables[0]
    assert table.name == "sales_data"
    assert table.source_filename == "Sales Data.csv"
    assert table.row_count == 2
    assert [c.name for c in table.columns] == ["customer_name", "total"]
    rows = session.conn.execute('SELECT * FROM "sales_data" ORDER BY customer_name').fetchall()
    assert rows == [("Alice", 10), ("Bob", 20)]


def test_batch_with_duplicate_filenames_suffixes_table_names():
    session = make_session()
    content = b"a,b\n1,2\n"

    tables = ingest_upload_batch(
        session, [("data.csv", content), ("data.csv", content)]
    )

    assert [t.name for t in tables] == ["data", "data_2"]


def test_reuploading_same_filename_replaces_existing_table():
    session = make_session()
    first = ingest_upload_batch(session, [("data.csv", b"a,b\n1,2\n")])
    assert first[0].row_count == 1

    second = ingest_upload_batch(session, [("data.csv", b"a,b\n1,2\n3,4\n5,6\n")])

    assert second[0].name == "data"
    assert second[0].row_count == 3
    assert len(session.table_sources) == 1


def test_non_csv_extension_rejected():
    session = make_session()
    with pytest.raises(HTTPException) as exc_info:
        ingest_upload_batch(session, [("data.txt", b"a,b\n1,2\n")])
    assert exc_info.value.status_code == 400
    assert session.table_sources == {}


def test_empty_file_rejected():
    session = make_session()
    with pytest.raises(HTTPException) as exc_info:
        ingest_upload_batch(session, [("empty.csv", b"")])
    assert exc_info.value.status_code == 400


def test_unparseable_csv_rejected():
    session = make_session()
    with pytest.raises(HTTPException):
        ingest_upload_batch(session, [("bad.csv", b'"unterminated quote\nrow')])


def test_oversized_file_rejected(monkeypatch):
    session = make_session()
    from app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "0")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc_info:
            ingest_upload_batch(session, [("data.csv", b"a,b\n1,2\n")])
        assert exc_info.value.status_code == 400
    finally:
        config.get_settings.cache_clear()


def test_one_bad_file_in_batch_aborts_the_whole_batch():
    session = make_session()
    with pytest.raises(HTTPException):
        ingest_upload_batch(
            session,
            [("good.csv", b"a,b\n1,2\n"), ("bad.txt", b"a,b\n1,2\n")],
        )
    assert session.table_sources == {}


def test_list_tables_reflects_current_session_state():
    session = make_session()
    ingest_upload_batch(session, [("data.csv", b"a,b\n1,2\n")])

    tables = list_tables(session)

    assert len(tables) == 1
    assert tables[0].name == "data"
    assert tables[0].row_count == 1
