from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.positions import PositionRead


class PositionsAnalysisSummaryRead(BaseModel):
    date_from: date
    date_to: date
    broker_name: str

    trades_pnl: float = 0.0
    trades_count: int = 0
    trades_win_rate: float = 0.0

    turnover_buy: float = 0.0
    turnover_sell: float = 0.0
    turnover_total: float = 0.0

    open_positions_count: int = 0


class MonthlyPositionsAnalyticsRead(BaseModel):
    month: str  # YYYY-MM

    trades_pnl: float = 0.0
    trades_count: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0

    turnover_buy: float = 0.0
    turnover_sell: float = 0.0
    turnover_total: float = 0.0


class SymbolPnlRead(BaseModel):
    symbol: str
    product: Optional[str] = None
    pnl: float = 0.0
    trades: int = 0
    win_rate: float = 0.0


class ClosedTradeRead(BaseModel):
    symbol: str
    product: Optional[str] = None
    opened_at: datetime
    closed_at: datetime
    pnl: float


class PositionsAnalysisRead(BaseModel):
    summary: PositionsAnalysisSummaryRead
    monthly: List[MonthlyPositionsAnalyticsRead]
    winners: List[SymbolPnlRead]
    losers: List[SymbolPnlRead]
    open_positions: List[PositionRead]
    closed_trades: List[ClosedTradeRead]


__all__ = [
    "PositionsAnalysisSummaryRead",
    "MonthlyPositionsAnalyticsRead",
    "SymbolPnlRead",
    "ClosedTradeRead",
    "PositionsAnalysisRead",
]
