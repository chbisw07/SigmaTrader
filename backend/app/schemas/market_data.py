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


__all__ = ["CandlePoint"]
