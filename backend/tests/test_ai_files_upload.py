from __future__ import annotations

import io
import os
import tempfile

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app


client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-ai-files-secret"
    # Use a temp upload directory so tests don't write into repo.
    tmpdir = tempfile.mkdtemp(prefix="st-ai-files-")
    os.environ["ST_AI_FILE_UPLOAD_DIR"] = tmpdir
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Register + login to establish a session cookie.
    client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "pw12345", "display_name": "Alice"},
    )
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw12345"})
    client.cookies.clear()
    client.cookies.update(resp.cookies)


def test_upload_csv_returns_summary() -> None:
    payload = "a,b,c\n1,2,3\n4,5,6\n"
    files = [("files", ("test.csv", payload.encode("utf-8"), "text/csv"))]
    resp = client.post("/api/ai/files", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert len(data["files"]) == 1
    meta = data["files"][0]
    assert meta["filename"] == "test.csv"
    assert meta["summary"]["kind"] == "csv"
    assert meta["summary"]["columns"] == ["a", "b", "c"]
    assert meta["summary"]["row_count"] == 2
    assert len(meta["summary"]["preview_rows"]) == 2


def test_upload_xlsx_returns_summary() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["sym", "qty"])
    ws.append(["ABC", 10])
    ws.append(["XYZ", 5])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    files = [("files", ("test.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    resp = client.post("/api/ai/files", files=files)
    assert resp.status_code == 200
    meta = resp.json()["files"][0]
    assert meta["filename"] == "test.xlsx"
    assert meta["summary"]["kind"] == "xlsx"
    assert "Sheet1" in meta["summary"]["sheets"]
    assert meta["summary"]["columns"] == ["sym", "qty"]
    assert meta["summary"]["row_count"] == 2
