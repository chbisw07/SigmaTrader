from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict
from app.schemas.groups import GroupDetailRead
from app.schemas.orders import OrderRead


class BasketBuyItem(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=128)
    exchange: Optional[str] = Field(None, max_length=32)
    qty: int = Field(..., ge=1)


class BasketBuyRequest(BaseModel):
    broker_name: str = "zerodha"
    product: str = "CNC"
    order_type: Literal["MARKET"] = "MARKET"
    execution_target: Literal["LIVE", "PAPER"] = "LIVE"
    items: List[BasketBuyItem] = Field(default_factory=list)


class BasketBuyResponse(BaseModel):
    portfolio_group: GroupDetailRead
    orders: List[OrderRead] = Field(default_factory=list)
    created_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


__all__ = ["BasketBuyItem", "BasketBuyRequest", "BasketBuyResponse"]

