from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import BaseModel


class MarketCalendarRowRead(BaseModel):
    date: date
    exchange: str
    session_type: str
    open_time: Optional[time] = None
    close_time: Optional[time] = None
    notes: Optional[str] = None


__all__ = ["MarketCalendarRowRead"]
