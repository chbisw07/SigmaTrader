from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.pydantic_compat import PYDANTIC_V2, ConfigDict


class PositionRead(BaseModel):
    id: int
    symbol: str
    product: str
    qty: float
    avg_price: float
    pnl: float
    last_updated: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


class HoldingRead(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    exchange: Optional[str] = None
    last_price: Optional[float] = None
    pnl: Optional[float] = None
    last_purchase_date: Optional[datetime] = None
    total_pnl_percent: Optional[float] = None
    today_pnl_percent: Optional[float] = None


__all__ = ["PositionRead", "HoldingRead"]
