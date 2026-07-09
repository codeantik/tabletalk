from datetime import timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services.session_manager import get_session_manager

client = TestClient(app)


def _create_session() -> str:
    response = client.post("/api/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


def test_create_session_returns_id_and_expiry():
    response = client.post("/api/sessions")
    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body and body["session_id"]
    assert body["expires_at"] > body["created_at"]


def test_upload_then_get_tables_roundtrip():
    session_id = _create_session()
    files = [("files", ("orders.csv", b"Order ID,Amount\n1,9.99\n2,19.99\n", "text/csv"))]

    upload_response = client.post(f"/api/sessions/{session_id}/upload", files=files)
    assert upload_response.status_code == 200
    upload_body = upload_response.json()
    assert upload_body["session_id"] == session_id
    assert len(upload_body["tables"]) == 1
    table = upload_body["tables"][0]
    assert table["name"] == "orders"
    assert table["row_count"] == 2
    assert [c["name"] for c in table["columns"]] == ["order_id", "amount"]

    tables_response = client.get(f"/api/sessions/{session_id}/tables")
    assert tables_response.status_code == 200
    assert tables_response.json()["tables"][0]["name"] == "orders"


def test_upload_multiple_files_in_one_request():
    session_id = _create_session()
    files = [
        ("files", ("orders.csv", b"a,b\n1,2\n", "text/csv")),
        ("files", ("customers.csv", b"x,y\n1,2\n", "text/csv")),
    ]

    response = client.post(f"/api/sessions/{session_id}/upload", files=files)
    assert response.status_code == 200
    names = {t["name"] for t in response.json()["tables"]}
    assert names == {"orders", "customers"}


def test_upload_to_unknown_session_returns_404():
    files = [("files", ("orders.csv", b"a,b\n1,2\n", "text/csv"))]
    response = client.post("/api/sessions/does-not-exist/upload", files=files)
    assert response.status_code == 404


def test_upload_invalid_file_returns_400_and_leaves_session_unchanged():
    session_id = _create_session()
    files = [("files", ("notes.txt", b"hello", "text/plain"))]

    response = client.post(f"/api/sessions/{session_id}/upload", files=files)
    assert response.status_code == 400

    tables_response = client.get(f"/api/sessions/{session_id}/tables")
    assert tables_response.json()["tables"] == []


def test_get_tables_for_unknown_session_returns_404():
    response = client.get("/api/sessions/does-not-exist/tables")
    assert response.status_code == 404


def test_delete_session_then_access_returns_404():
    session_id = _create_session()
    delete_response = client.delete(f"/api/sessions/{session_id}")
    assert delete_response.status_code == 204

    response = client.get(f"/api/sessions/{session_id}/tables")
    assert response.status_code == 404


def test_expired_session_returns_404_on_next_request():
    session_id = _create_session()
    manager = get_session_manager()
    record = manager.get_session(session_id)
    record.last_accessed_at -= timedelta(minutes=manager._ttl.total_seconds() / 60 + 1)

    response = client.get(f"/api/sessions/{session_id}/tables")
    assert response.status_code == 404
