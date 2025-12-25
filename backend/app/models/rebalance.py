from __future__ import annotations

from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
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


class RebalancePolicy(Base):
    __tablename__ = "rebalance_policies"

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "group_id",
            name="ux_rebalance_policies_owner_group",
        ),
        Index("ix_rebalance_policies_owner_id", "owner_id"),
        Index("ix_rebalance_policies_group_id", "group_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Canonical default broker scope for UI suggestions. Runs can override.
    broker_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="zerodha",
    )

    # JSON blob of policy knobs (bands, budget defaults, constraints, etc.)
    policy_json: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    schedules: Mapped[List["RebalanceSchedule"]] = relationship(
        back_populates="policy",
        cascade="all,delete-orphan",
        order_by="RebalanceSchedule.created_at",
    )


class RebalanceSchedule(Base):
    __tablename__ = "rebalance_schedules"

    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            name="ux_rebalance_schedules_policy_id",
        ),
        Index("ix_rebalance_schedules_policy_id", "policy_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rebalance_policies.id", ondelete="CASCADE"),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_json: Mapped[Optional[str]] = mapped_column(Text())
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    policy: Mapped[RebalancePolicy] = relationship(back_populates="schedules")


class RebalanceRun(Base):
    __tablename__ = "rebalance_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'EXECUTED', 'FAILED')",
            name="ck_rebalance_runs_status",
        ),
        CheckConstraint(
            "mode IN ('MANUAL', 'AUTO')",
            name="ck_rebalance_runs_mode",
        ),
        UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="ux_rebalance_runs_owner_idempotency",
        ),
        Index("ix_rebalance_runs_owner_id", "owner_id"),
        Index("ix_rebalance_runs_group_id", "group_id"),
        Index(
            "ix_rebalance_runs_group_broker_time",
            "group_id",
            "broker_name",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CREATED")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="MANUAL")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128))

    policy_snapshot_json: Mapped[Optional[str]] = mapped_column(Text())
    inputs_snapshot_json: Mapped[Optional[str]] = mapped_column(Text())
    summary_json: Mapped[Optional[str]] = mapped_column(Text())
    error_message: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    orders: Mapped[List["RebalanceRunOrder"]] = relationship(
        back_populates="run",
        cascade="all,delete-orphan",
        order_by="RebalanceRunOrder.id",
    )


class RebalanceRunOrder(Base):
    __tablename__ = "rebalance_run_orders"

    __table_args__ = (
        Index("ix_rebalance_run_orders_run_id", "run_id"),
        Index("ix_rebalance_run_orders_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rebalance_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_price: Mapped[Optional[float]] = mapped_column(Float)
    estimated_notional: Mapped[Optional[float]] = mapped_column(Float)

    target_weight: Mapped[Optional[float]] = mapped_column(Float)
    live_weight: Mapped[Optional[float]] = mapped_column(Float)
    drift: Mapped[Optional[float]] = mapped_column(Float)
    current_value: Mapped[Optional[float]] = mapped_column(Float)
    desired_value: Mapped[Optional[float]] = mapped_column(Float)
    delta_value: Mapped[Optional[float]] = mapped_column(Float)
    scale: Mapped[Optional[float]] = mapped_column(Float)

    reason_json: Mapped[Optional[str]] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROPOSED")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    run: Mapped[RebalanceRun] = relationship(back_populates="orders")


__all__ = [
    "RebalancePolicy",
    "RebalanceSchedule",
    "RebalanceRun",
    "RebalanceRunOrder",
]
