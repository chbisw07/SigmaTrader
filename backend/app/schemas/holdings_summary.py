from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.pydantic_compat import PYDANTIC_V2, ConfigDict


class HoldingsSummarySnapshotRead(BaseModel):
    id: int
    user_id: int
    broker_name: str
    as_of_date: date
    captured_at: datetime

    holdings_count: int

    funds_available: Optional[float] = None
    invested: Optional[float] = None
    equity_value: Optional[float] = None
    account_value: Optional[float] = None

    total_pnl_pct: Optional[float] = None
    today_pnl_pct: Optional[float] = None
    overall_win_rate: Optional[float] = None
    today_win_rate: Optional[float] = None

    alpha_annual_pct: Optional[float] = None
    beta: Optional[float] = None

    cagr_1y_pct: Optional[float] = None
    cagr_2y_pct: Optional[float] = None
    cagr_1y_coverage_pct: Optional[float] = None
    cagr_2y_coverage_pct: Optional[float] = None

    benchmark_symbol: Optional[str] = None
    benchmark_exchange: Optional[str] = None
    risk_free_rate_pct: Optional[float] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)


class HoldingsSummarySnapshotsMeta(BaseModel):
    broker_name: str
    today: date
    min_date: Optional[date] = None
    max_date: Optional[date] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")


__all__ = ["HoldingsSummarySnapshotRead", "HoldingsSummarySnapshotsMeta"]

