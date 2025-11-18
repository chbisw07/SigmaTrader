from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StrategyBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    execution_mode: str = Field("MANUAL", regex="^(AUTO|MANUAL)$")
    execution_target: str = Field("LIVE", regex="^(LIVE|PAPER)$")
    paper_poll_interval_sec: Optional[int] = Field(
        None, ge=15, le=4 * 60 * 60
    )  # 15s to 4h
    enabled: bool = True


class StrategyCreate(StrategyBase):
    pass


class StrategyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    execution_mode: Optional[str] = Field(None, regex="^(AUTO|MANUAL)$")
    execution_target: Optional[str] = Field(None, regex="^(LIVE|PAPER)$")
    paper_poll_interval_sec: Optional[int] = Field(None, ge=15, le=4 * 60 * 60)
    enabled: Optional[bool] = None


class StrategyRead(StrategyBase):
    id: int

    class Config:
        orm_mode = True


__all__ = ["StrategyCreate", "StrategyUpdate", "StrategyRead"]
