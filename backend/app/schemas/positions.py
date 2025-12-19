from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.pydantic_compat import PYDANTIC_V2, ConfigDict


class PositionRead(BaseModel):
    id: int
    symbol: str
    exchange: str
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


class PositionSnapshotRead(BaseModel):
    id: int
    as_of_date: date
    captured_at: datetime
    symbol: str
    exchange: str
    product: str

    qty: float
    remaining_qty: float = 0.0
    traded_qty: float = 0.0
    order_type: str = "—"
    avg_price: float
    pnl: float

    avg_buy_price: Optional[float] = None
    avg_sell_price: Optional[float] = None
    pnl_value: Optional[float] = None
    pnl_pct: Optional[float] = None
    ltp: Optional[float] = None
    today_pnl: Optional[float] = None
    today_pnl_pct: Optional[float] = None

    last_price: Optional[float] = None
    close_price: Optional[float] = None
    value: Optional[float] = None
    m2m: Optional[float] = None
    unrealised: Optional[float] = None
    realised: Optional[float] = None

    buy_qty: Optional[float] = None
    buy_avg_price: Optional[float] = None
    sell_qty: Optional[float] = None
    sell_avg_price: Optional[float] = None

    day_buy_qty: Optional[float] = None
    day_buy_avg_price: Optional[float] = None
    day_sell_qty: Optional[float] = None
    day_sell_avg_price: Optional[float] = None

    holding_qty: Optional[float] = None

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


__all__ = ["PositionRead", "PositionSnapshotRead", "HoldingRead"]
