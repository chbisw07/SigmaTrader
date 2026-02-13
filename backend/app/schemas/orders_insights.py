from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class OrdersInsightsSummaryRead(BaseModel):
    date_from: date
    date_to: date
    broker_name: Optional[str] = None

    tv_alerts: int = 0

    decisions_total: int = 0
    decisions_placed: int = 0
    decisions_blocked: int = 0
    decisions_from_tv: int = 0

    orders_total: int = 0
    orders_executed: int = 0
    orders_failed: int = 0
    orders_rejected_risk: int = 0
    orders_waiting: int = 0

    decision_products: Dict[str, int] = Field(default_factory=dict)
    decision_sides: Dict[str, int] = Field(default_factory=dict)

    order_products: Dict[str, int] = Field(default_factory=dict)
    order_sides: Dict[str, int] = Field(default_factory=dict)
    origins: Dict[str, int] = Field(default_factory=dict)
    statuses: Dict[str, int] = Field(default_factory=dict)


class OrdersInsightsDayRead(BaseModel):
    day: date

    tv_alerts: int = 0

    decisions_total: int = 0
    decisions_placed: int = 0
    decisions_blocked: int = 0
    decisions_from_tv: int = 0

    orders_total: int = 0
    orders_executed: int = 0
    orders_failed: int = 0
    orders_rejected_risk: int = 0
    orders_waiting: int = 0

    decision_products: Dict[str, int] = Field(default_factory=dict)
    decision_sides: Dict[str, int] = Field(default_factory=dict)

    order_products: Dict[str, int] = Field(default_factory=dict)
    order_sides: Dict[str, int] = Field(default_factory=dict)


class OrdersInsightsSymbolRead(BaseModel):
    symbol: str
    buys: int = 0
    sells: int = 0
    orders_total: int = 0
    orders_executed: int = 0
    decisions_blocked: int = 0


class OrdersInsightsReasonRead(BaseModel):
    reason: str
    count: int = 0


class OrdersInsightsRead(BaseModel):
    summary: OrdersInsightsSummaryRead
    daily: List[OrdersInsightsDayRead] = Field(default_factory=list)
    top_symbols: List[OrdersInsightsSymbolRead] = Field(default_factory=list)
    top_block_reasons: List[OrdersInsightsReasonRead] = Field(default_factory=list)


__all__ = [
    "OrdersInsightsSummaryRead",
    "OrdersInsightsDayRead",
    "OrdersInsightsSymbolRead",
    "OrdersInsightsReasonRead",
    "OrdersInsightsRead",
]
