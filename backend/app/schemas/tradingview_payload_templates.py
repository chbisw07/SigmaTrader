from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TradingViewHintFieldV1(BaseModel):
    key: str
    type: Literal["string", "number", "boolean", "enum"]
    value: Any = None
    enum_options: list[str] | None = None


class TradingViewAlertPayloadBuilderConfigV1(BaseModel):
    version: Literal["1.0"] = "1.0"
    signal: dict[str, Any] = Field(default_factory=dict)
    signal_enabled: dict[str, bool] = Field(default_factory=dict)
    hints: list[TradingViewHintFieldV1] = Field(default_factory=list)


class TradingViewAlertPayloadTemplateSummary(BaseModel):
    id: int
    name: str
    updated_at: datetime


class TradingViewAlertPayloadTemplateRead(BaseModel):
    id: int
    name: str
    config: TradingViewAlertPayloadBuilderConfigV1
    updated_at: datetime


class TradingViewAlertPayloadTemplateUpsert(BaseModel):
    name: str
    config: TradingViewAlertPayloadBuilderConfigV1


__all__ = [
    "TradingViewAlertPayloadBuilderConfigV1",
    "TradingViewAlertPayloadTemplateRead",
    "TradingViewAlertPayloadTemplateSummary",
    "TradingViewAlertPayloadTemplateUpsert",
    "TradingViewHintFieldV1",
]

