from __future__ import annotations

from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Group(Base):
    __tablename__ = "groups"

    __table_args__ = (
        CheckConstraint(
            "kind IN ('WATCHLIST', 'MODEL_PORTFOLIO', 'HOLDINGS_VIEW', 'PORTFOLIO')",
            name="ck_groups_kind",
        ),
        Index("ix_groups_owner_id", "owner_id"),
        Index("ix_groups_kind", "kind"),
        UniqueConstraint("owner_id", "name", name="ux_groups_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="WATCHLIST")
    description: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    members: Mapped[List["GroupMember"]] = relationship(
        back_populates="group",
        cascade="all,delete-orphan",
        order_by="GroupMember.created_at",
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "symbol",
            "exchange",
            name="ux_group_members_group_symbol_exchange",
        ),
        Index("ix_group_members_group_id", "group_id"),
        Index("ix_group_members_symbol_exchange", "symbol", "exchange"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(32))

    # Fraction of the total (0.0 to 1.0). When NULL, the group is treated as
    # equal-weight.
    target_weight: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text())

    # Basket/portfolio metadata: the planned quantity and reference price captured
    # at creation time (used for "since creation" P&L and amount required).
    reference_qty: Mapped[Optional[int]] = mapped_column(Integer)
    reference_price: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    group: Mapped[Group] = relationship(back_populates="members")


__all__ = ["Group", "GroupMember"]
