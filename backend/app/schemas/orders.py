from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

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
    "REJECTED_RISK",
]

ExecutionMode = Literal["MANUAL", "AUTO"]
ExecutionTarget = Literal["LIVE", "PAPER"]


class OrderRead(BaseModel):
    id: int
    alert_id: Optional[int]
    strategy_id: Optional[int]
    portfolio_group_id: Optional[int] = None
    broker_name: str = "zerodha"
    symbol: str
    exchange: Optional[str]
    side: str
    qty: float
    price: Optional[float]
    trigger_price: Optional[float]
    trigger_percent: Optional[float]
    order_type: str
    product: str
    gtt: bool
    synthetic_gtt: bool = False
    trigger_operator: Optional[str] = None
    armed_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    last_seen_price: Optional[float] = None
    triggered_at: Optional[datetime] = None
    status: AllowedOrderStatus
    mode: str
    execution_target: ExecutionTarget = "LIVE"
    simulated: bool
    created_at: datetime
    updated_at: datetime
    broker_order_id: Optional[str] = None
    # Backward-compatible legacy field (deprecated).
    zerodha_order_id: Optional[str] = None
    broker_account_id: Optional[str] = None
    error_message: Optional[str] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

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
    trigger_price: Optional[float] = None
    trigger_percent: Optional[float] = None
    side: Optional[Literal["BUY", "SELL"]] = None
    order_type: Optional[Literal["MARKET", "LIMIT", "SL", "SL-M"]] = None
    product: Optional[str] = None
    gtt: Optional[bool] = None


class ManualOrderCreate(BaseModel):
    """Payload for creating a new manual WAITING order."""

    broker_name: str = "zerodha"
    portfolio_group_id: Optional[int] = None
    symbol: str
    exchange: Optional[str] = None
    side: Literal["BUY", "SELL"]
    qty: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    order_type: Literal["MARKET", "LIMIT", "SL", "SL-M"] = "MARKET"
    product: str = "CNC"
    gtt: bool = False
    mode: ExecutionMode = "MANUAL"
    execution_target: ExecutionTarget = "LIVE"


__all__ = [
    "OrderRead",
    "OrderStatusUpdate",
    "OrderUpdate",
    "ManualOrderCreate",
    "AllowedOrderStatus",
    "ExecutionMode",
    "ExecutionTarget",
]
