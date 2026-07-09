"""CSV ingestion: validation, column-name cleaning, and load into DuckDB.

Ingestion is all-or-nothing per upload request: every file is validated and
parsed first, and only if all of them succeed are tables created/replaced in
the session's DuckDB connection. This keeps a failed batch from leaving the
session in a half-updated state.
"""

import io
import re
from dataclasses import dataclass, field

import duckdb
import pandas as pd
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.services.session_manager import SessionRecord

_NON_IDENTIFIER_CHARS = re.compile(r"[^a-z0-9_]+")
_REPEATED_UNDERSCORES = re.compile(r"_+")


class CsvValidationError(Exception):
    """A single file in an upload batch failed validation or parsing."""

    def __init__(self, filename: str, detail: str):
        self.filename = filename
        self.detail = detail
        super().__init__(f"{filename}: {detail}")


@dataclass
class ColumnInfo:
    name: str
    type: str


@dataclass
class TableInfo:
    name: str
    source_filename: str
    row_count: int
    columns: list[ColumnInfo] = field(default_factory=list)


def normalize_identifier(name: str, fallback: str) -> str:
    """Lowercase, strip, and collapse a raw header/filename into a safe SQL identifier."""
    name = name.strip().lower()
    name = _NON_IDENTIFIER_CHARS.sub("_", name)
    name = _REPEATED_UNDERSCORES.sub("_", name).strip("_")
    if not name:
        name = fallback
    if name[0].isdigit():
        name = f"{fallback}_{name}"
    return name


def dedupe_names(names: list[str]) -> list[str]:
    """Suffix repeated identifiers (_2, _3, ...) so every name is unique."""
    used: set[str] = set()
    result = []
    for name in names:
        candidate = name
        suffix = 2
        while candidate in used:
            candidate = f"{name}_{suffix}"
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result


def _read_and_validate_csv(filename: str, content: bytes) -> pd.DataFrame:
    settings = get_settings()
    if not filename.lower().endswith(".csv"):
        raise CsvValidationError(filename, "Only .csv files are supported")
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise CsvValidationError(
            filename, f"File exceeds the {settings.max_upload_size_mb}MB upload limit"
        )
    if not content.strip():
        raise CsvValidationError(filename, "File is empty")
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise CsvValidationError(filename, f"Could not parse CSV: {exc}") from exc
    if df.shape[1] == 0:
        raise CsvValidationError(filename, "CSV has no columns")
    return df


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = [normalize_identifier(str(col), "column") for col in df.columns]
    df = df.copy()
    df.columns = dedupe_names(normalized)
    return df


def _ingest_dataframe(
    conn: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame, source_filename: str
) -> TableInfo:
    conn.register("_incoming", df)
    try:
        conn.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM _incoming')
    finally:
        conn.unregister("_incoming")
    row_count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    columns = [
        ColumnInfo(name=row[0], type=row[1])
        for row in conn.execute(f'DESCRIBE "{table_name}"').fetchall()
    ]
    return TableInfo(
        name=table_name, source_filename=source_filename, row_count=row_count, columns=columns
    )


def list_tables(session: SessionRecord) -> list[TableInfo]:
    """Describe every table currently loaded in a session, straight from DuckDB."""
    tables = []
    for table_name, source_filename in session.table_sources.items():
        row_count = session.conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        columns = [
            ColumnInfo(name=row[0], type=row[1])
            for row in session.conn.execute(f'DESCRIBE "{table_name}"').fetchall()
        ]
        tables.append(
            TableInfo(
                name=table_name,
                source_filename=source_filename,
                row_count=row_count,
                columns=columns,
            )
        )
    return tables


def ingest_upload_batch(
    session: SessionRecord, files: list[tuple[str, bytes]]
) -> list[TableInfo]:
    """Validate, clean, and load a batch of CSV files into a session's DuckDB.

    Raises HTTPException(400) listing every failing file if any file in the
    batch is invalid; nothing is written to the session in that case.
    """
    parsed: list[tuple[str, pd.DataFrame]] = []
    errors: list[dict[str, str]] = []
    for filename, content in files:
        try:
            df = _read_and_validate_csv(filename, content)
        except CsvValidationError as exc:
            errors.append({"filename": exc.filename, "detail": exc.detail})
            continue
        parsed.append((filename, _clean_columns(df)))

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "One or more files failed validation", "errors": errors},
        )

    # Re-uploading a filename that already backs a table replaces that table
    # in place; any other name collision (including two files in this same
    # batch sharing a name) gets a numeric suffix instead.
    table_name_by_filename: dict[str, str] = {}
    for name, source in session.table_sources.items():
        table_name_by_filename.setdefault(source, name)

    used_table_names = set(session.table_sources.keys())
    claimed_filenames: set[str] = set()
    tables: list[TableInfo] = []
    for filename, df in parsed:
        if filename in table_name_by_filename and filename not in claimed_filenames:
            table_name = table_name_by_filename[filename]
        else:
            stem = filename.rsplit(".", 1)[0]
            base_name = normalize_identifier(stem, "table")
            table_name = base_name
            suffix = 2
            while table_name in used_table_names:
                table_name = f"{base_name}_{suffix}"
                suffix += 1
        claimed_filenames.add(filename)
        used_table_names.add(table_name)

        table_info = _ingest_dataframe(session.conn, table_name, df, filename)
        session.table_sources[table_name] = filename
        tables.append(table_info)

    return tables
