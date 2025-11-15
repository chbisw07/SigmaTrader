from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, root_validator, validator


class TradeDetails(BaseModel):
    order_action: str = Field(..., alias="order_action")
    quantity: Optional[float] = None
    price: Optional[float] = None
    product: Optional[str] = None

    @root_validator(pre=True)
    def _map_alternate_field_names(cls, values: dict[str, Any]) -> dict[str, Any]:
        # Support TradingView payloads that use order_contracts / order_price
        if "quantity" not in values and "order_contracts" in values:
            values["quantity"] = values.get("order_contracts")
        if "price" not in values and "order_price" in values:
            values["price"] = values.get("order_price")
        return values

    @validator("order_action")
    def _normalize_order_action(cls, v: str) -> str:
        normalized = v.upper()
        if normalized not in {"BUY", "SELL"}:
            raise ValueError("order_action must be BUY or SELL")
        return normalized


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

    @root_validator(pre=True)
    def _normalize_platform(cls, values: dict[str, Any]) -> dict[str, Any]:
        platform = values.get("platform")
        # Accept either a string or a list like ["fyers"]
        if isinstance(platform, list) and platform:
            values["platform"] = str(platform[0])
        return values


__all__ = ["TradeDetails", "TradingViewWebhookPayload"]
