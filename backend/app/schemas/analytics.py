from __future__ import annotations

from datetime import datetime
from typing import List, Optional

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


class CorrelationPair(BaseModel):
    symbol_x: str
    symbol_y: str
    correlation: float


class SymbolCorrelationStats(BaseModel):
    symbol: str
    average_correlation: Optional[float]
    most_correlated_symbol: Optional[str] = None
    most_correlated_value: Optional[float] = None
    cluster: Optional[str] = None
    weight_fraction: Optional[float] = None


class CorrelationClusterSummary(BaseModel):
    id: str
    symbols: List[str]
    weight_fraction: Optional[float]
    average_internal_correlation: Optional[float]
    average_to_others: Optional[float]


class HoldingsCorrelationResult(BaseModel):
    symbols: List[str]
    matrix: List[List[Optional[float]]]
    window_days: int
    observations: int
    average_correlation: Optional[float]
    diversification_rating: str
    summary: str
    recommendations: List[str]
    top_positive: List[CorrelationPair]
    top_negative: List[CorrelationPair]
    symbol_stats: List[SymbolCorrelationStats]
    clusters: List[CorrelationClusterSummary]
    effective_independent_bets: Optional[float]


__all__ = [
    "AnalyticsSummary",
    "AnalyticsRebuildResponse",
    "AnalyticsSummaryQuery",
    "AnalyticsTradeRead",
    "CorrelationPair",
    "SymbolCorrelationStats",
    "CorrelationClusterSummary",
    "HoldingsCorrelationResult",
]
