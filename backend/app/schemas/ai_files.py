from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AiFileSummary(BaseModel):
    kind: str = "unknown"  # csv|xlsx|unknown
    columns: List[str] = Field(default_factory=list)
    row_count: int = 0
    preview_rows: List[Dict[str, Any]] = Field(default_factory=list)
    sheets: List[str] = Field(default_factory=list)
    active_sheet: Optional[str] = None


class AiFileMeta(BaseModel):
    file_id: str
    filename: str
    size: int
    mime: Optional[str] = None
    created_at: datetime
    summary: AiFileSummary = Field(default_factory=AiFileSummary)


class AiFileUploadResponse(BaseModel):
    files: List[AiFileMeta] = Field(default_factory=list)


__all__ = ["AiFileMeta", "AiFileSummary", "AiFileUploadResponse"]

