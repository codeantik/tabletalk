from datetime import datetime

from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime


class ColumnSchema(BaseModel):
    name: str
    type: str
    missing_count: int = 0
    missing_pct: float = 0.0
    outlier_count: int | None = None
    coerced_from: str | None = None


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


class MessageRequest(BaseModel):
    question: str


class ChartSeriesPoint(BaseModel):
    name: str
    value: float


class ChartDataPoint(BaseModel):
    x: str
    series: list[ChartSeriesPoint]


class ChartResponse(BaseModel):
    type: str
    data: list[ChartDataPoint]


class TableResponse(BaseModel):
    columns: list[str]
    rows: list[list]


class MessageResponse(BaseModel):
    session_id: str
    question: str
    created_at: datetime
    sql_used: str | None = None
    intent: str | None = None
    text: str | None = None
    chart: ChartResponse | None = None
    table: TableResponse | None = None
    error: str | None = None
    row_limit_applied: bool = False


class MessagesHistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageResponse]
