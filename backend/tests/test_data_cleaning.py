from datetime import datetime, timezone

import duckdb
import pandas as pd
import pytest

from app.services.csv_ingestion import ingest_upload_batch
from app.services.data_cleaning import clean_values, compute_quality
from app.services.session_manager import SessionRecord


def make_session() -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        session_id="test-session",
        conn=duckdb.connect(database=":memory:"),
        created_at=now,
        last_accessed_at=now,
    )


def test_missing_sentinels_normalized_to_nan():
    df = pd.DataFrame({"note": ["ok", "N/A", "null", "-", "", "  unknown  "]})

    cleaned, coerced_from = clean_values(df)

    assert cleaned["note"].isna().sum() == 5
    assert coerced_from == {}


def test_currency_column_coerced_to_numeric():
    values = [f"${i},000.00" for i in range(1, 25)]
    df = pd.DataFrame({"amount": values})

    cleaned, coerced_from = clean_values(df)

    assert coerced_from == {"amount": "string"}
    assert pd.api.types.is_numeric_dtype(cleaned["amount"])
    assert cleaned["amount"].iloc[0] == 1000.0


def test_mixed_column_below_threshold_is_not_coerced():
    # 20 numeric-looking values + 5 genuinely non-numeric -> 80% success, below the 95% bar.
    values = [str(i) for i in range(20)] + ["red", "green", "blue", "yellow", "black"]
    df = pd.DataFrame({"code": values})

    cleaned, coerced_from = clean_values(df)

    assert coerced_from == {}
    assert cleaned["code"].dtype == object


def test_small_sample_not_coerced_even_if_all_numeric():
    df = pd.DataFrame({"amount": ["1", "2", "3"]})

    cleaned, coerced_from = clean_values(df)

    assert coerced_from == {}
    assert cleaned["amount"].dtype == object


def test_date_column_coerced():
    values = [f"2024-01-{i:02d}" for i in range(1, 25)]
    df = pd.DataFrame({"order_date": values})

    cleaned, coerced_from = clean_values(df)

    assert coerced_from == {"order_date": "string"}
    assert pd.api.types.is_datetime64_any_dtype(cleaned["order_date"])


def test_failed_coercions_become_null_not_dropped_rows():
    values = [str(i) for i in range(1, 25)] + ["oops"]
    df = pd.DataFrame({"amount": values})

    cleaned, coerced_from = clean_values(df)

    assert coerced_from == {"amount": "string"}
    assert len(cleaned) == len(values)
    assert cleaned["amount"].isna().sum() == 1


def test_ingest_upload_batch_populates_quality_report():
    session = make_session()
    rows = [f"{i},{100 + i}" for i in range(1, 25)]
    content = ("id,amount\n" + "\n".join(rows) + "\nN/A,unknown\n").encode()

    tables = ingest_upload_batch(session, [("orders.csv", content)])

    quality = session.table_quality[tables[0].name]
    assert quality["id"].missing_count == 1
    assert quality["amount"].missing_count == 1


def test_compute_quality_flags_outliers_via_sql():
    session = make_session()
    values = list(range(1, 25)) + [10_000]
    rows = "\n".join(str(v) for v in values)
    content = f"amount\n{rows}\n".encode()

    tables = ingest_upload_batch(session, [("data.csv", content)])

    quality = compute_quality(
        session.conn, tables[0].name, tables[0].columns, coerced_from={}
    )
    assert quality["amount"].outlier_count == 1


def test_native_path_reports_sentinel_strings_as_missing_without_mutating(monkeypatch):
    from app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("LARGE_FILE_THRESHOLD_MB", "0")
    config.get_settings.cache_clear()
    try:
        session = make_session()
        content = b"id,note\n1,ok\n2,N/A\n3,null\n"

        tables = ingest_upload_batch(session, [("data.csv", content)])

        quality = session.table_quality[tables[0].name]
        assert quality["note"].missing_count == 2
        raw = session.conn.execute(f'SELECT note FROM "{tables[0].name}" ORDER BY id').fetchall()
        assert raw == [("ok",), ("N/A",), ("null",)]
    finally:
        config.get_settings.cache_clear()
