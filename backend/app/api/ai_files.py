from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.ai_files import AiFileMeta, AiFileUploadResponse
from app.services.ai.files_store import DEFAULT_MAX_BYTES, create_file, get_file_meta, get_file_path

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.post("/files", response_model=AiFileUploadResponse)
def upload_ai_files(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(get_current_user),
) -> AiFileUploadResponse:
    max_bytes = DEFAULT_MAX_BYTES
    raw_limit = os.getenv("ST_AI_FILE_MAX_BYTES")
    if raw_limit:
        try:
            max_bytes = int(raw_limit)
        except Exception:
            max_bytes = DEFAULT_MAX_BYTES

    out: list[AiFileMeta] = []
    for f in files:
        out.append(create_file(db, settings, user_id=int(user.id), upload=f, max_bytes=max_bytes))
    return AiFileUploadResponse(files=out)


@router.get("/files/{file_id}/meta", response_model=AiFileMeta)
def get_ai_file_meta(
    file_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> AiFileMeta:
    meta = get_file_meta(db, file_id=file_id, user_id=int(user.id))
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    return meta


@router.get("/files/{file_id}/download")
def download_ai_file(
    file_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> FileResponse:
    res = get_file_path(db, file_id=file_id, user_id=int(user.id))
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    filename, path = res
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk.")
    return FileResponse(path, filename=filename)


__all__ = ["router"]

