from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

ExecutionMode = Literal["AUTO", "MANUAL"]
ExecutionTarget = Literal["LIVE", "PAPER"]


class StrategyBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    execution_mode: ExecutionMode = "MANUAL"
    execution_target: ExecutionTarget = "LIVE"
    paper_poll_interval_sec: Optional[int] = Field(
        None, ge=15, le=4 * 60 * 60
    )  # 15s to 4h
    enabled: bool = True


class StrategyCreate(StrategyBase):
    pass


class StrategyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    execution_mode: Optional[ExecutionMode] = None
    execution_target: Optional[ExecutionTarget] = None
    paper_poll_interval_sec: Optional[int] = Field(None, ge=15, le=4 * 60 * 60)
    enabled: Optional[bool] = None


class StrategyRead(StrategyBase):
    id: int

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = ["StrategyCreate", "StrategyUpdate", "StrategyRead"]
