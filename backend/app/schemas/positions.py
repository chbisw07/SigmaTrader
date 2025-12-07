from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PositionRead(BaseModel):
    id: int
    symbol: str
    product: str
    qty: float
    avg_price: float
    pnl: float
    last_updated: datetime

    class Config:
        orm_mode = True


class HoldingRead(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    last_price: Optional[float] = None
    pnl: Optional[float] = None
    last_purchase_date: Optional[datetime] = None


__all__ = ["PositionRead", "HoldingRead"]
