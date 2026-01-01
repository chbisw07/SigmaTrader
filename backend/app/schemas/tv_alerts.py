from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.pydantic_compat import PYDANTIC_V2, ConfigDict


class TvAlertRead(BaseModel):
    id: int
    user_id: Optional[int] = None
    strategy_id: Optional[int] = None
    strategy_name: Optional[str] = None
    symbol: str
    exchange: Optional[str] = None
    interval: Optional[str] = None
    action: str
    qty: Optional[float] = None
    price: Optional[float] = None
    platform: str
    source: str
    reason: Optional[str] = None
    received_at: datetime
    bar_time: Optional[datetime] = None
    raw_payload: str

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = ["TvAlertRead"]
