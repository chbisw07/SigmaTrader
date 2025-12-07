from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

IndicatorType = Literal[
    "RSI",
    "MA",
    "MA_CROSS",
    "VOLATILITY",
    "ATR",
    "PERF_PCT",
    "VOLUME_RATIO",
    "VWAP",
]

OperatorType = Literal["GT", "LT", "CROSS_ABOVE", "CROSS_BELOW", "BETWEEN", "OUTSIDE"]
TriggerMode = Literal["ONCE", "ONCE_PER_BAR", "EVERY_TIME"]
ActionType = Literal["ALERT_ONLY", "SELL_PERCENT", "BUY_QUANTITY"]
LogicType = Literal["AND", "OR"]
UniverseType = Literal["HOLDINGS"]


class IndicatorCondition(BaseModel):
    """Single indicator condition inside a rule."""

    indicator: IndicatorType
    operator: OperatorType
    threshold_1: float
    threshold_2: Optional[float] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class IndicatorRuleBase(BaseModel):
    """Common fields for creating/updating indicator rules."""

    name: Optional[str] = None
    symbol: Optional[str] = None
    universe: Optional[UniverseType] = None
    exchange: Optional[str] = None
    timeframe: str = "1d"

    logic: LogicType = "AND"
    conditions: List[IndicatorCondition]

    trigger_mode: TriggerMode = "ONCE"
    action_type: ActionType = "ALERT_ONLY"
    action_params: Dict[str, Any] = Field(default_factory=dict)

    expires_at: Optional[datetime] = None
    enabled: bool = True


class IndicatorRuleCreate(IndicatorRuleBase):
    strategy_id: Optional[int] = None


class IndicatorRuleUpdate(BaseModel):
    name: Optional[str] = None
    symbol: Optional[str] = None
    universe: Optional[UniverseType] = None
    exchange: Optional[str] = None
    timeframe: Optional[str] = None
    logic: Optional[LogicType] = None
    conditions: Optional[List[IndicatorCondition]] = None
    trigger_mode: Optional[TriggerMode] = None
    action_type: Optional[ActionType] = None
    action_params: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    enabled: Optional[bool] = None


class IndicatorRuleRead(IndicatorRuleBase):
    id: int
    strategy_id: Optional[int] = None
    last_triggered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:  # Pydantic v1
        orm_mode = True


__all__ = [
    "IndicatorType",
    "OperatorType",
    "TriggerMode",
    "ActionType",
    "LogicType",
    "UniverseType",
    "IndicatorCondition",
    "IndicatorRuleBase",
    "IndicatorRuleCreate",
    "IndicatorRuleUpdate",
    "IndicatorRuleRead",
]
