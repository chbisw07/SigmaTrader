from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

GoalLabel = Literal["CORE", "TRADE", "THEME", "HEDGE", "INCOME", "PARKING"]
TargetType = Literal["PCT_FROM_AVG_BUY", "PCT_FROM_LTP", "ABSOLUTE_PRICE"]


class HoldingGoalBase(BaseModel):
    label: GoalLabel
    review_date: date
    target_type: TargetType | None = None
    target_value: float | None = None
    note: str | None = None


class HoldingGoalUpsert(BaseModel):
    symbol: str
    exchange: str | None = None
    broker_name: str | None = None
    label: GoalLabel
    review_date: date | None = None
    target_type: TargetType | None = None
    target_value: float | None = None
    note: str | None = None


class HoldingGoalRead(HoldingGoalBase):
    id: int
    user_id: int
    broker_name: str
    symbol: str
    exchange: str
    created_at: datetime
    updated_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = ["GoalLabel", "TargetType", "HoldingGoalRead", "HoldingGoalUpsert"]
