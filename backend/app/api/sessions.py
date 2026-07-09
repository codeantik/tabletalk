from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.models.schemas import (
    ColumnSchema,
    MessageRequest,
    MessageResponse,
    MessagesHistoryResponse,
    SessionResponse,
    TablesResponse,
    TableSchema,
    UploadResponse,
)
from app.services.conversation_store import ConversationTurn
from app.services.csv_ingestion import TableInfo, ingest_upload_batch, list_tables
from app.services.query_engine import run_nl_query
from app.services.rate_limiter import RateLimitExceeded, get_rate_limiter
from app.services.session_manager import SessionRecord, get_session_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_table_schema(table: TableInfo) -> TableSchema:
    return TableSchema(
        name=table.name,
        source_filename=table.source_filename,
        row_count=table.row_count,
        columns=[ColumnSchema(name=col.name, type=col.type) for col in table.columns],
    )


def _to_session_response(record: SessionRecord) -> SessionResponse:
    manager = get_session_manager()
    return SessionResponse(
        session_id=record.session_id,
        created_at=record.created_at,
        expires_at=manager.expires_at(record),
    )


def _turn_to_message_response(session_id: str, turn: ConversationTurn) -> MessageResponse:
    return MessageResponse(
        session_id=session_id,
        question=turn.question,
        created_at=turn.created_at,
        sql_used=turn.sql,
        intent=turn.intent,
        text=turn.text,
        chart=turn.chart,
        table=turn.table,
        error=turn.error,
        row_limit_applied=turn.row_limit_applied,
    )


@router.post("", response_model=SessionResponse, status_code=201)
def create_session() -> SessionResponse:
    record = get_session_manager().create_session()
    return _to_session_response(record)


@router.post("/{session_id}/upload", response_model=UploadResponse)
async def upload_csvs(session_id: str, files: list[UploadFile] = File(...)) -> UploadResponse:
    session = get_session_manager().get_session(session_id)
    file_contents = [(f.filename or "", await f.read()) for f in files]
    tables = ingest_upload_batch(session, file_contents)
    return UploadResponse(session_id=session_id, tables=[_to_table_schema(t) for t in tables])


@router.get("/{session_id}/tables", response_model=TablesResponse)
def get_tables(session_id: str) -> TablesResponse:
    session = get_session_manager().get_session(session_id)
    tables = list_tables(session)
    return TablesResponse(session_id=session_id, tables=[_to_table_schema(t) for t in tables])


@router.post("/{session_id}/messages", response_model=MessageResponse)
def post_message(session_id: str, body: MessageRequest) -> MessageResponse:
    session = get_session_manager().get_session(session_id)
    try:
        get_rate_limiter().check(session_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc

    result = run_nl_query(session, get_settings(), body.question)
    return MessageResponse(
        session_id=session_id,
        question=body.question,
        created_at=result.created_at,
        sql_used=result.sql,
        intent=result.intent,
        text=result.text,
        chart=result.chart,
        table=result.table,
        error=result.error,
        row_limit_applied=result.row_limit_applied,
    )


@router.get("/{session_id}/messages", response_model=MessagesHistoryResponse)
def get_messages(session_id: str) -> MessagesHistoryResponse:
    session = get_session_manager().get_session(session_id)
    return MessagesHistoryResponse(
        session_id=session_id,
        messages=[_turn_to_message_response(session_id, turn) for turn in session.turns],
    )


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    get_session_manager().close_session(session_id)
