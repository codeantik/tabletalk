from fastapi import APIRouter, File, UploadFile

from app.models.schemas import ColumnSchema, SessionResponse, TablesResponse, TableSchema, UploadResponse
from app.services.csv_ingestion import TableInfo, ingest_upload_batch, list_tables
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


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    get_session_manager().close_session(session_id)
