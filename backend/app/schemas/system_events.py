from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SystemEventRead(BaseModel):
    id: int
    level: str
    category: str
    message: str
    details: Optional[str]
    correlation_id: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


__all__ = ["SystemEventRead"]
