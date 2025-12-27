from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

BacktestKind = Literal["SIGNAL", "PORTFOLIO", "EXECUTION"]
BacktestStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]


class UniverseSymbol(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: str = Field(default="NSE", min_length=1)


class BacktestUniverse(BaseModel):
    mode: Literal["HOLDINGS", "GROUP", "BOTH"] = "GROUP"
    broker_name: str = "zerodha"
    group_id: Optional[int] = None
    symbols: list[UniverseSymbol] = Field(default_factory=list)


class BacktestRunCreate(BaseModel):
    kind: BacktestKind
    title: Optional[str] = None
    universe: BacktestUniverse = Field(default_factory=BacktestUniverse)
    config: dict[str, Any] = Field(default_factory=dict)


class BacktestRunRead(BaseModel):
    id: int
    owner_id: Optional[int] = None
    kind: str
    status: str
    title: Optional[str] = None
    config: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, obj) -> "BacktestRunRead":
        config = {}
        result = None
        try:
            config = json.loads(obj.config_json or "{}")
        except Exception:
            config = {}
        if obj.result_json:
            try:
                result = json.loads(obj.result_json)
            except Exception:
                result = None

        return cls(
            id=obj.id,
            owner_id=obj.owner_id,
            kind=obj.kind,
            status=obj.status,
            title=obj.title,
            config=config,
            result=result,
            error_message=obj.error_message,
            started_at=obj.started_at,
            finished_at=obj.finished_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class EodCandleLoadRequest(BaseModel):
    symbols: list[UniverseSymbol] = Field(min_items=1)
    start: datetime
    end: datetime
    allow_fetch: bool = True


class EodCandleLoadResponse(BaseModel):
    dates: list[str]
    prices: dict[str, list[Optional[float]]]
    missing_symbols: list[str] = Field(default_factory=list)


class BacktestRunsDeleteRequest(BaseModel):
    ids: list[int] = Field(min_items=1)


class BacktestRunsDeleteResponse(BaseModel):
    deleted_ids: list[int] = Field(default_factory=list)
    forbidden_ids: list[int] = Field(default_factory=list)
    missing_ids: list[int] = Field(default_factory=list)


__all__ = [
    "BacktestKind",
    "BacktestRunCreate",
    "BacktestRunRead",
    "BacktestRunsDeleteRequest",
    "BacktestRunsDeleteResponse",
    "BacktestStatus",
    "BacktestUniverse",
    "EodCandleLoadRequest",
    "EodCandleLoadResponse",
    "UniverseSymbol",
]
