from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PortfolioAllocationRead(BaseModel):
    group_id: int
    group_name: str
    symbol: str
    exchange: str
    reference_qty: Optional[int] = None
    reference_price: Optional[float] = None


class PortfolioAllocationUpdate(BaseModel):
    group_id: int
    reference_qty: int = Field(ge=0)


class PortfolioAllocationReconcileRequest(BaseModel):
    broker_name: str = "zerodha"
    symbol: str
    exchange: Optional[str] = None
    updates: List[PortfolioAllocationUpdate] = Field(default_factory=list)


class PortfolioAllocationReconcileResponse(BaseModel):
    symbol: str
    exchange: str
    holding_qty: float
    allocated_total: float
    updated_groups: int


__all__ = [
    "PortfolioAllocationRead",
    "PortfolioAllocationUpdate",
    "PortfolioAllocationReconcileRequest",
    "PortfolioAllocationReconcileResponse",
]
