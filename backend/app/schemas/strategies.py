from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

ExecutionMode = Literal["AUTO", "MANUAL"]
ExecutionTarget = Literal["LIVE", "PAPER"]
StrategyScope = Literal["GLOBAL", "LOCAL"]


class StrategyBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    execution_mode: ExecutionMode = "MANUAL"
    execution_target: ExecutionTarget = "LIVE"
    paper_poll_interval_sec: Optional[int] = Field(
        None,
        ge=15,
        le=4 * 60 * 60,
    )  # 15s to 4h
    enabled: bool = True
    available_for_alert: bool = True

    # Optional reusable alert template information. For many strategies this
    # will remain empty; templates can later be attached to indicator rules.
    scope: Optional[StrategyScope] = None
    dsl_expression: Optional[str] = None


class StrategyCreate(StrategyBase):
    pass


class StrategyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    execution_mode: Optional[ExecutionMode] = None
    execution_target: Optional[ExecutionTarget] = None
    paper_poll_interval_sec: Optional[int] = Field(
        None,
        ge=15,
        le=4 * 60 * 60,
    )
    enabled: Optional[bool] = None
    available_for_alert: Optional[bool] = None
    scope: Optional[StrategyScope] = None
    dsl_expression: Optional[str] = None


class StrategyRead(StrategyBase):
    id: int
    scope: Optional[StrategyScope] = None
    dsl_expression: Optional[str] = None
    is_builtin: bool = False

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = [
    "ExecutionMode",
    "ExecutionTarget",
    "StrategyScope",
    "StrategyCreate",
    "StrategyUpdate",
    "StrategyRead",
]
