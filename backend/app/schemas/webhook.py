from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TradeDetails(BaseModel):
    order_action: Literal["BUY", "SELL"] = Field(..., alias="order_action")
    quantity: Optional[float] = None
    price: Optional[float] = None


class TradingViewWebhookPayload(BaseModel):
    """Pydantic model for TradingView webhook payloads.

    This is intentionally minimal for Sprint S03 / G01 and will be
    extended as we refine the alert schema.
    """

    secret: str
    platform: str = "TRADINGVIEW"
    strategy_name: str
    symbol: str
    exchange: Optional[str] = None
    interval: Optional[str] = None
    trade_details: TradeDetails
    bar_time: Optional[datetime] = None


__all__ = ["TradeDetails", "TradingViewWebhookPayload"]
