from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AnalyticsSummary(BaseModel):
    strategy_id: Optional[int]
    total_pnl: float
    trades: int
    win_rate: float
    avg_win: Optional[float]
    avg_loss: Optional[float]
    max_drawdown: float


class AnalyticsRebuildResponse(BaseModel):
    created: int


class AnalyticsSummaryQuery(BaseModel):
    strategy_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class AnalyticsTradeRead(BaseModel):
    id: int
    strategy_id: Optional[int]
    strategy_name: Optional[str]
    symbol: str
    product: str
    pnl: float
    opened_at: datetime
    closed_at: datetime


__all__ = [
    "AnalyticsSummary",
    "AnalyticsRebuildResponse",
    "AnalyticsSummaryQuery",
    "AnalyticsTradeRead",
]
