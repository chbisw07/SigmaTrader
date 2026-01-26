from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class RiskProfile(Base):
    __tablename__ = "risk_profiles"

    __table_args__ = (
        CheckConstraint("product IN ('CNC', 'MIS')", name="ck_risk_profiles_product"),
        CheckConstraint(
            "drawdown_mode IN ('SETTINGS_BY_CATEGORY')",
            name="ck_risk_profiles_drawdown_mode",
        ),
        UniqueConstraint("name", name="ux_risk_profiles_name"),
        Index("ix_risk_profiles_product_enabled", "product", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product: Mapped[str] = mapped_column(String(16), nullable=False, default="CNC")

    capital_per_trade: Mapped[float] = mapped_column(nullable=False, default=0.0)
    max_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_exposure_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)

    risk_per_trade_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    hard_risk_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)

    daily_loss_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    hard_daily_loss_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    max_consecutive_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    drawdown_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SETTINGS_BY_CATEGORY"
    )

    # Time controls (HH:MM, interpreted in IST for now).
    force_exit_time: Mapped[Optional[str]] = mapped_column(String(8))

    # MIS-only extensions (nullable for CNC).
    entry_cutoff_time: Mapped[Optional[str]] = mapped_column(String(8))
    force_squareoff_time: Mapped[Optional[str]] = mapped_column(String(8))
    max_trades_per_day: Mapped[Optional[int]] = mapped_column(Integer)
    max_trades_per_symbol_per_day: Mapped[Optional[int]] = mapped_column(Integer)
    min_bars_between_trades: Mapped[Optional[int]] = mapped_column(Integer)
    cooldown_after_loss_bars: Mapped[Optional[int]] = mapped_column(Integer)
    slippage_guard_bps: Mapped[Optional[float]] = mapped_column(nullable=True)
    gap_guard_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    order_type_policy: Mapped[Optional[str]] = mapped_column(String(32))
    leverage_mode: Mapped[Optional[str]] = mapped_column(String(16))
    max_effective_leverage: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_margin_used_pct: Mapped[Optional[float]] = mapped_column(nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SymbolRiskCategory(Base):
    __tablename__ = "symbol_risk_categories"

    __table_args__ = (
        CheckConstraint(
            "risk_category IN ('LC', 'MC', 'SC', 'ETF')",
            name="ck_symbol_risk_categories_category",
        ),
        UniqueConstraint(
            "user_id",
            "broker_name",
            "symbol",
            "exchange",
            name="ux_symbol_risk_categories_scope",
        ),
        Index(
            "ix_symbol_risk_categories_user_symbol",
            "user_id",
            "broker_name",
            "symbol",
            "exchange",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False, default="zerodha")
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False, default="NSE")
    risk_category: Mapped[str] = mapped_column(String(16), nullable=False, default="LC")

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class DrawdownThreshold(Base):
    __tablename__ = "drawdown_thresholds"

    __table_args__ = (
        CheckConstraint("product IN ('CNC', 'MIS')", name="ck_drawdown_thresholds_product"),
        CheckConstraint(
            "category IN ('LC', 'MC', 'SC', 'ETF')",
            name="ck_drawdown_thresholds_category",
        ),
        UniqueConstraint(
            "user_id",
            "product",
            "category",
            name="ux_drawdown_thresholds_scope",
        ),
        Index("ix_drawdown_thresholds_product_category", "product", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    product: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    caution_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    defense_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    hard_stop_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    __table_args__ = (
        UniqueConstraint("user_id", "as_of_date", name="ux_equity_snapshots_scope"),
        Index("ix_equity_snapshots_user_date", "user_id", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    equity: Mapped[float] = mapped_column(nullable=False, default=0.0)
    peak_equity: Mapped[float] = mapped_column(nullable=False, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AlertDecisionLog(Base):
    __tablename__ = "alert_decision_logs"

    __table_args__ = (
        Index("ix_alert_decision_logs_created", "created_at"),
        Index("ix_alert_decision_logs_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    alert_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False, default="ALERT")
    strategy_ref: Mapped[Optional[str]] = mapped_column(String(255))
    symbol: Mapped[Optional[str]] = mapped_column(String(128))
    exchange: Mapped[Optional[str]] = mapped_column(String(16))
    side: Mapped[Optional[str]] = mapped_column(String(8))
    trigger_price: Mapped[Optional[float]] = mapped_column(nullable=True)

    product_hint: Mapped[Optional[str]] = mapped_column(String(16))
    resolved_product: Mapped[Optional[str]] = mapped_column(String(16))
    risk_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("risk_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    risk_category: Mapped[Optional[str]] = mapped_column(String(16))
    drawdown_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    drawdown_state: Mapped[Optional[str]] = mapped_column(String(16))

    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="BLOCKED")
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


__all__ = [
    "AlertDecisionLog",
    "DrawdownThreshold",
    "EquitySnapshot",
    "RiskProfile",
    "SymbolRiskCategory",
]
