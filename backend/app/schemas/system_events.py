from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict


class SystemEventRead(BaseModel):
    id: int
    level: str
    category: str
    message: str
    details: Optional[str]
    correlation_id: Optional[str]
    created_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = ["SystemEventRead"]


class SystemEventsCleanupRequest(BaseModel):
    max_days: int = Field(default=7, ge=0)
    dry_run: bool = False

    def max_days_delta(self) -> timedelta:
        return timedelta(days=int(self.max_days))


class SystemEventsCleanupResponse(BaseModel):
    deleted: int
    remaining: int


__all__ = [
    "SystemEventRead",
    "SystemEventsCleanupRequest",
    "SystemEventsCleanupResponse",
]
