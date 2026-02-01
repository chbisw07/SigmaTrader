from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Float,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.holdings_exit.constants import (
    HOLDING_EXIT_DISPATCH_MODES,
    HOLDING_EXIT_EVENT_TYPES,
    HOLDING_EXIT_EXECUTION_TARGETS,
    HOLDING_EXIT_ORDER_TYPES,
    HOLDING_EXIT_PRICE_SOURCES,
    HOLDING_EXIT_SIZE_MODES,
    HOLDING_EXIT_STATUSES,
    HOLDING_EXIT_TRIGGER_KINDS,
    sql_in,
)


class HoldingExitSubscription(Base):
    __tablename__ = "holding_exit_subscriptions"

    __table_args__ = (
        CheckConstraint(
            f"trigger_kind IN {sql_in(HOLDING_EXIT_TRIGGER_KINDS)}",
            name="ck_holding_exit_subscriptions_trigger_kind",
        ),
        CheckConstraint(
            f"price_source IN {sql_in(HOLDING_EXIT_PRICE_SOURCES)}",
            name="ck_holding_exit_subscriptions_price_source",
        ),
        CheckConstraint(
            f"size_mode IN {sql_in(HOLDING_EXIT_SIZE_MODES)}",
            name="ck_holding_exit_subscriptions_size_mode",
        ),
        CheckConstraint(
            f"order_type IN {sql_in(HOLDING_EXIT_ORDER_TYPES)}",
            name="ck_holding_exit_subscriptions_order_type",
        ),
        CheckConstraint(
            f"dispatch_mode IN {sql_in(HOLDING_EXIT_DISPATCH_MODES)}",
            name="ck_holding_exit_subscriptions_dispatch_mode",
        ),
        CheckConstraint(
            f"execution_target IN {sql_in(HOLDING_EXIT_EXECUTION_TARGETS)}",
            name="ck_holding_exit_subscriptions_execution_target",
        ),
        CheckConstraint(
            "product IN ('CNC', 'MIS')",
            name="ck_holding_exit_subscriptions_product",
        ),
        CheckConstraint(
            f"status IN {sql_in(HOLDING_EXIT_STATUSES)}",
            name="ck_holding_exit_subscriptions_status",
        ),
        UniqueConstraint(
            "user_id",
            "broker_name",
            "exchange",
            "symbol",
            "product",
            "trigger_kind",
            "trigger_value",
            "size_mode",
            "size_value",
            name="ux_holding_exit_subscriptions_dedup",
        ),
        Index(
            "ix_holding_exit_subscriptions_status_broker_user",
            "status",
            "broker_name",
            "user_id",
        ),
        Index(
            "ix_holding_exit_subscriptions_symbol_scope",
            "broker_name",
            "exchange",
            "symbol",
            "product",
        ),
        Index("ix_holding_exit_subscriptions_next_eval_at", "next_eval_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    broker_name: Mapped[str] = mapped_column(
        String(32), nullable=False, default="zerodha"
    )
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False, default="NSE")
    product: Mapped[str] = mapped_column(String(16), nullable=False, default="CNC")

    trigger_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_value: Mapped[float] = mapped_column(Float, nullable=False)
    price_source: Mapped[str] = mapped_column(String(16), nullable=False, default="LTP")

    size_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    size_value: Mapped[float] = mapped_column(Float, nullable=False)
    min_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    order_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MARKET"
    )
    dispatch_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MANUAL"
    )
    execution_target: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LIVE"
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    pending_order_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )

    last_error: Mapped[Optional[str]] = mapped_column(Text())
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    next_eval_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    trigger_key: Mapped[Optional[str]] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class HoldingExitEvent(Base):
    __tablename__ = "holding_exit_events"

    __table_args__ = (
        CheckConstraint(
            f"event_type IN {sql_in(HOLDING_EXIT_EVENT_TYPES)}",
            name="ck_holding_exit_events_event_type",
        ),
        Index("ix_holding_exit_events_sub_ts", "subscription_id", "event_ts"),
        Index("ix_holding_exit_events_type_ts", "event_type", "event_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("holding_exit_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_ts: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    details_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    price_snapshot_json: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


__all__ = ["HoldingExitSubscription", "HoldingExitEvent"]
