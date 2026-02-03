from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class RiskGlobalConfig(Base):
    """Unified risk settings: global toggles and shared baselines.

    This is the single user-facing "Risk Settings" system. Other tables (profiles,
    thresholds, symbol categories, overrides) are inputs into the unified resolver.
    """

    __tablename__ = "risk_global_config"

    __table_args__ = (
        # Single-row table; enforced by unique "singleton" key.
        UniqueConstraint("singleton_key", name="ux_risk_global_config_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    singleton_key: Mapped[str] = mapped_column(String(16), nullable=False, default="GLOBAL")

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # When ON: explicitly user-created manual orders can bypass risk blocks/clamps.
    manual_override_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Baseline equity used for drawdown and daily loss calculations (INR).
    baseline_equity_inr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class RiskSourceOverride(Base):
    """Optional per-source overrides that layer on top of product profiles.

    These are applied at enforcement time with precedence:
      explicit override -> product profile -> global defaults

    MANUAL is intentionally not configurable here: it is handled via the global
    manual override toggle.
    """

    __tablename__ = "risk_source_overrides"

    __table_args__ = (
        CheckConstraint(
            "source_bucket IN ('TRADINGVIEW', 'SIGMATRADER')",
            name="ck_risk_source_overrides_source_bucket",
        ),
        CheckConstraint(
            "product IN ('CNC', 'MIS')",
            name="ck_risk_source_overrides_product",
        ),
        UniqueConstraint(
            "source_bucket",
            "product",
            name="ux_risk_source_overrides_scope",
        ),
        Index("ix_risk_source_overrides_source_product", "source_bucket", "product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    product: Mapped[str] = mapped_column(String(16), nullable=False, default="CNC")

    # When false, this (source, product) is blocked for new entries.
    allow_product: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Execution safety (per order)
    allow_short_selling: Mapped[Optional[bool]] = mapped_column(Boolean)
    max_order_value_pct: Mapped[Optional[float]] = mapped_column(Float)
    max_order_value_abs: Mapped[Optional[float]] = mapped_column(Float)
    max_quantity_per_order: Mapped[Optional[float]] = mapped_column(Float)

    # Optional overrides of profile fields (kept in sync with risk_profiles columns).
    capital_per_trade: Mapped[Optional[float]] = mapped_column(Float)
    max_positions: Mapped[Optional[int]] = mapped_column(Integer)
    max_exposure_pct: Mapped[Optional[float]] = mapped_column(Float)

    daily_loss_pct: Mapped[Optional[float]] = mapped_column(Float)
    hard_daily_loss_pct: Mapped[Optional[float]] = mapped_column(Float)
    max_consecutive_losses: Mapped[Optional[int]] = mapped_column(Integer)

    # Trade frequency + time controls
    entry_cutoff_time: Mapped[Optional[str]] = mapped_column(String(8))
    force_squareoff_time: Mapped[Optional[str]] = mapped_column(String(8))
    max_trades_per_day: Mapped[Optional[int]] = mapped_column(Integer)
    max_trades_per_symbol_per_day: Mapped[Optional[int]] = mapped_column(Integer)
    min_bars_between_trades: Mapped[Optional[int]] = mapped_column(Integer)
    cooldown_after_loss_bars: Mapped[Optional[int]] = mapped_column(Integer)

    slippage_guard_bps: Mapped[Optional[float]] = mapped_column(Float)
    gap_guard_pct: Mapped[Optional[float]] = mapped_column(Float)
    order_type_policy: Mapped[Optional[str]] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["RiskGlobalConfig", "RiskSourceOverride"]

