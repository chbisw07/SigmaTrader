from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

ScheduleFrequency = Literal["WEEKLY", "MONTHLY", "QUARTERLY", "CUSTOM_DAYS"]
RollToTradingDay = Literal["NEXT", "PREV", "NONE"]
DayOfMonth = Union[int, Literal["LAST"]]


class RebalanceScheduleConfig(BaseModel):
    frequency: ScheduleFrequency = "MONTHLY"
    time_local: str = Field(
        "15:10", description="HH:MM (24h) in the configured timezone."
    )
    timezone: str = "Asia/Kolkata"

    weekday: Optional[int] = Field(
        4,
        ge=0,
        le=6,
        description="Only used for WEEKLY: Monday=0 ... Sunday=6. Default Friday=4.",
    )
    day_of_month: Optional[DayOfMonth] = Field(
        "LAST",
        description="Only used for MONTHLY/QUARTERLY: 'LAST' or 1..31.",
    )
    interval_days: Optional[int] = Field(
        30,
        ge=1,
        description="Only used for CUSTOM_DAYS.",
    )
    roll_to_trading_day: RollToTradingDay = "NEXT"


class RebalanceScheduleRead(BaseModel):
    group_id: int
    enabled: bool
    config: RebalanceScheduleConfig
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class RebalanceScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[RebalanceScheduleConfig] = None


__all__ = [
    "ScheduleFrequency",
    "RollToTradingDay",
    "DayOfMonth",
    "RebalanceScheduleConfig",
    "RebalanceScheduleRead",
    "RebalanceScheduleUpdate",
]
