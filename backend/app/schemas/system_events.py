from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

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
