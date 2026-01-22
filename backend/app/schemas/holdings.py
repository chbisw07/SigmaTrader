from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

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


class HoldingGoalImportMapping(BaseModel):
    symbol_column: str
    exchange_column: str | None = None
    label_column: str | None = None
    label_default: GoalLabel | None = None
    review_date_column: str | None = None
    review_date_default_days: int | None = Field(default=None, ge=1, le=730)
    target_value_column: str | None = None
    target_type: TargetType | None = None
    note_column: str | None = None


class HoldingGoalImportRequest(BaseModel):
    broker_name: str | None = None
    mapping: HoldingGoalImportMapping
    rows: list[dict[str, str]]
    holdings_symbols: list[str] | None = None


class HoldingGoalImportError(BaseModel):
    row_index: int
    symbol: str | None = None
    reason: str


class HoldingGoalImportResult(BaseModel):
    matched: int
    updated: int
    created: int
    skipped: int
    errors: list[HoldingGoalImportError] = []


class HoldingGoalImportPresetCreate(BaseModel):
    name: str
    mapping: HoldingGoalImportMapping


class HoldingGoalImportPresetRead(BaseModel):
    id: int
    name: str
    mapping: HoldingGoalImportMapping
    created_at: datetime
    updated_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = [
    "GoalLabel",
    "TargetType",
    "HoldingGoalRead",
    "HoldingGoalUpsert",
    "HoldingGoalImportMapping",
    "HoldingGoalImportRequest",
    "HoldingGoalImportResult",
    "HoldingGoalImportError",
    "HoldingGoalImportPresetCreate",
    "HoldingGoalImportPresetRead",
]
