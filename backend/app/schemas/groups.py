from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

GroupKind = Literal["WATCHLIST", "MODEL_PORTFOLIO", "HOLDINGS_VIEW", "PORTFOLIO"]
BasketAllocationMode = Literal["WEIGHT", "AMOUNT", "QTY"]


class GroupBase(BaseModel):
    name: str = Field(..., max_length=255)
    kind: GroupKind = "WATCHLIST"
    description: Optional[str] = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    kind: Optional[GroupKind] = None
    description: Optional[str] = None


class BasketConfigUpdate(BaseModel):
    funds: Optional[float] = Field(None, ge=0.0, description="Basket funds in INR.")
    allocation_mode: Optional[BasketAllocationMode] = None


class GroupMemberBase(BaseModel):
    symbol: str = Field(..., max_length=128)
    exchange: Optional[str] = Field(None, max_length=32)
    target_weight: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Fraction of total (0.0 to 1.0).",
    )
    reference_qty: Optional[int] = Field(
        None,
        ge=0,
        description="Planned quantity for basket/portfolio membership (optional).",
    )
    reference_price: Optional[float] = Field(
        None,
        gt=0.0,
        description="Reference price captured at creation time (optional).",
    )
    notes: Optional[str] = None
    allocation_amount: Optional[float] = Field(
        None,
        ge=0.0,
        description="Amount input (INR) for Amount mode (optional).",
    )
    allocation_qty: Optional[int] = Field(
        None,
        ge=0,
        description="Qty input for Qty mode (optional).",
    )


class GroupMemberCreate(GroupMemberBase):
    pass


class GroupMemberUpdate(BaseModel):
    target_weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    reference_qty: Optional[int] = Field(None, ge=0)
    reference_price: Optional[float] = Field(None, gt=0.0)
    weight_locked: Optional[bool] = None
    notes: Optional[str] = None
    allocation_amount: Optional[float] = Field(None, ge=0.0)
    allocation_qty: Optional[int] = Field(None, ge=0)


class GroupMemberRead(BaseModel):
    symbol: str
    exchange: Optional[str] = None
    target_weight: Optional[float] = None
    reference_qty: Optional[int] = None
    reference_price: Optional[float] = None
    frozen_price: Optional[float] = None
    weight_locked: bool = False
    notes: Optional[str] = None
    allocation_amount: Optional[float] = None
    allocation_qty: Optional[int] = None

    id: int
    group_id: int
    created_at: datetime
    updated_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class GroupRead(GroupBase):
    id: int
    owner_id: Optional[int] = None
    member_count: int = 0
    funds: Optional[float] = None
    allocation_mode: Optional[str] = None
    frozen_at: Optional[datetime] = None
    origin_basket_id: Optional[int] = None
    bought_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class GroupDetailRead(GroupRead):
    members: List[GroupMemberRead] = []


class GroupMembershipsRead(BaseModel):
    # symbol -> list of group names
    memberships: dict[str, List[str]]


__all__ = [
    "GroupKind",
    "BasketAllocationMode",
    "BasketConfigUpdate",
    "GroupCreate",
    "GroupUpdate",
    "GroupRead",
    "GroupDetailRead",
    "GroupMemberCreate",
    "GroupMemberUpdate",
    "GroupMemberRead",
    "GroupMembershipsRead",
]
