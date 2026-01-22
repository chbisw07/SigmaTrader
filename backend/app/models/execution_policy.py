from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class ExecutionPolicyState(Base):
    __tablename__ = "execution_policy_state"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "strategy_ref",
            "symbol",
            "product",
            name="ux_execution_policy_state_scope",
        ),
        Index("ix_execution_policy_state_user_strategy", "user_id", "strategy_ref"),
        Index("ix_execution_policy_state_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # NOTE: Orders may have user_id NULL in some single-user flows. We store 0
    # for such orders so scope uniqueness remains deterministic under SQLite.
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strategy_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    # Canonical symbol key, typically EXCHANGE:SYMBOL (uppercased).
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    product: Mapped[str] = mapped_column(String(16), nullable=False, default="MIS")

    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    interval_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="persisted"
    )
    default_interval_logged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    inflight_order_id: Mapped[int | None] = mapped_column(Integer)
    inflight_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    inflight_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    trades_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_trade_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_trade_bar_index: Mapped[int | None] = mapped_column(Integer)

    consecutive_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_loss_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_loss_bar_index: Mapped[int | None] = mapped_column(Integer)

    paused_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    paused_reason: Mapped[str | None] = mapped_column(String(255))

    # Lightweight position tracker to compute trade-level PnL and loss streaks.
    open_side: Mapped[str | None] = mapped_column(String(8))
    open_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    open_avg_price: Mapped[float | None] = mapped_column(Float)
    open_realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["ExecutionPolicyState"]
