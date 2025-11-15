from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

AllowedOrderStatus = Literal[
    "WAITING",
    "VALIDATED",
    "SENDING",
    "SENT",
    "FAILED",
    "EXECUTED",
    "PARTIALLY_EXECUTED",
    "CANCELLED",
    "REJECTED",
]


class OrderRead(BaseModel):
    id: int
    alert_id: Optional[int]
    strategy_id: Optional[int]
    symbol: str
    exchange: Optional[str]
    side: str
    qty: float
    price: Optional[float]
    order_type: str
    product: str
    gtt: bool
    status: AllowedOrderStatus
    mode: str
    simulated: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class OrderStatusUpdate(BaseModel):
    status: Literal["WAITING", "CANCELLED"]


__all__ = ["OrderRead", "OrderStatusUpdate", "AllowedOrderStatus"]
