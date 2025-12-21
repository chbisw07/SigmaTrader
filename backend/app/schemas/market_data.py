from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CandlePoint(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketSymbol(BaseModel):
    symbol: str
    exchange: str
    name: str | None = None


__all__ = ["CandlePoint", "MarketSymbol"]
