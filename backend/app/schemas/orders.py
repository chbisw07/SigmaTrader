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
    zerodha_order_id: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        orm_mode = True


class OrderStatusUpdate(BaseModel):
    status: Literal["WAITING", "CANCELLED"]


class OrderUpdate(BaseModel):
    """Editable fields for a manual queue order.

    For now we restrict editing to order-level parameters that do not
    change the alert/strategy linkage.
    """

    qty: Optional[float] = None
    price: Optional[float] = None
    order_type: Optional[Literal["MARKET", "LIMIT"]] = None
    product: Optional[str] = None


__all__ = ["OrderRead", "OrderStatusUpdate", "OrderUpdate", "AllowedOrderStatus"]
