from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

IndicatorType = Literal[
    "PRICE",
    "RSI",
    "MA",
    "MA_CROSS",
    "VOLATILITY",
    "ATR",
    "PERF_PCT",
    "VOLUME_RATIO",
    "VWAP",
    "PVT",
    "PVT_SLOPE",
]

OperatorType = Literal[
    "GT",
    "LT",
    "CROSS_ABOVE",
    "CROSS_BELOW",
    "BETWEEN",
    "OUTSIDE",
    "MOVE_UP_PCT",
    "MOVE_DOWN_PCT",
]
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
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    timeframe: str = "1d"

    logic: LogicType = "AND"
    conditions: List[IndicatorCondition]
    dsl_expression: Optional[str] = None

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
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    timeframe: Optional[str] = None
    logic: Optional[LogicType] = None
    conditions: Optional[List[IndicatorCondition]] = None
    trigger_mode: Optional[TriggerMode] = None
    action_type: Optional[ActionType] = None
    action_params: Optional[Dict[str, Any]] = None
    dsl_expression: Optional[str] = None
    expires_at: Optional[datetime] = None
    enabled: Optional[bool] = None


class IndicatorRuleRead(IndicatorRuleBase):
    id: int
    strategy_id: Optional[int] = None
    last_triggered_at: Optional[datetime] = None
    last_evaluated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
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
