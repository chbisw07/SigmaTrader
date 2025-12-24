from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.alerts_v3 import AlertVariableDef


class ScreenerRunRequest(BaseModel):
    include_holdings: bool = False
    group_ids: List[int] = Field(default_factory=list)
    variables: List[AlertVariableDef] = Field(default_factory=list)
    condition_dsl: str
    evaluation_cadence: Optional[str] = None
    signal_strategy_version_id: Optional[int] = None
    signal_strategy_output: Optional[str] = None
    signal_strategy_params: Dict[str, Any] = Field(default_factory=dict)


class ScreenerRow(BaseModel):
    symbol: str
    exchange: str
    matched: bool
    missing_data: bool = False
    error: Optional[str] = None

    last_price: Optional[float] = None
    rsi_14_1d: Optional[float] = None
    sma_20_1d: Optional[float] = None
    sma_50_1d: Optional[float] = None

    variables: Dict[str, Optional[float]] = Field(default_factory=dict)


class ScreenerRunRead(BaseModel):
    id: int
    status: str
    evaluation_cadence: str

    total_symbols: int
    evaluated_symbols: int
    matched_symbols: int
    missing_symbols: int

    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    rows: Optional[List[ScreenerRow]] = None

    signal_strategy_version_id: Optional[int] = None
    signal_strategy_output: Optional[str] = None
    signal_strategy_params: Dict[str, Any] = Field(default_factory=dict)


class ScreenerCreateGroupRequest(BaseModel):
    name: str
    kind: str = "WATCHLIST"
    description: Optional[str] = None
