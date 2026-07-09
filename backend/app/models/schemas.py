from datetime import datetime

from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime


class ColumnSchema(BaseModel):
    name: str
    type: str


class TableSchema(BaseModel):
    name: str
    source_filename: str
    row_count: int
    columns: list[ColumnSchema]


class UploadResponse(BaseModel):
    session_id: str
    tables: list[TableSchema]


class TablesResponse(BaseModel):
    session_id: str
    tables: list[TableSchema]


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    session_id: str
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list] | None = None
    explanation: str | None = None
    error: str | None = None
    row_limit_applied: bool = False
