from __future__ import annotations

from datetime import UTC
from datetime import date as date_type
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
from app.db.types import UTCDateTime


class Strategy(Base):
    __tablename__ = "strategies"

    __table_args__ = (
        CheckConstraint(
            "execution_mode IN ('AUTO', 'MANUAL')",
            name="ck_strategies_execution_mode",
        ),
        CheckConstraint(
            "execution_target IN ('LIVE', 'PAPER')",
            name="ck_strategies_execution_target",
        ),
        Index("ix_strategies_execution_mode", "execution_mode"),
        Index("ix_strategies_execution_target", "execution_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text())

    # Ownership and scoping for reusable templates.
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    scope: Mapped[Optional[str]] = mapped_column(String(16))  # GLOBAL or LOCAL

    # Optional expression template for indicator-based alerts.
    dsl_expression: Mapped[Optional[str]] = mapped_column(Text())
    expression_json: Mapped[Optional[str]] = mapped_column(Text())

    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    execution_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MANUAL"
    )
    execution_target: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LIVE"
    )
    paper_poll_interval_sec: Mapped[Optional[int]] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    available_for_alert: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    alerts: Mapped[List["Alert"]] = relationship(
        back_populates="strategy", cascade="all,delete-orphan"
    )
    risk_settings: Mapped[List["RiskSettings"]] = relationship(
        back_populates="strategy", cascade="all,delete-orphan"
    )
    orders: Mapped[List["Order"]] = relationship(back_populates="strategy")


class RiskSettings(Base):
    __tablename__ = "risk_settings"

    __table_args__ = (
        UniqueConstraint(
            "scope",
            "strategy_id",
            name="ux_risk_settings_scope_strategy",
        ),
        CheckConstraint(
            "scope IN ('GLOBAL', 'STRATEGY')", name="ck_risk_settings_scope"
        ),
        CheckConstraint(
            "(scope = 'GLOBAL' AND strategy_id IS NULL) OR "
            "(scope = 'STRATEGY' AND strategy_id IS NOT NULL)",
            name="ck_risk_settings_scope_strategy",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="STRATEGY")
    strategy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=True
    )

    max_order_value: Mapped[Optional[float]] = mapped_column(Float)
    max_quantity_per_order: Mapped[Optional[float]] = mapped_column(Float)
    max_daily_loss: Mapped[Optional[float]] = mapped_column(Float)
    allow_short_selling: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    max_open_positions: Mapped[Optional[int]] = mapped_column(Integer)
    clamp_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="CLAMP")

    symbol_whitelist: Mapped[Optional[str]] = mapped_column(Text())
    symbol_blacklist: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    strategy: Mapped[Optional[Strategy]] = relationship(back_populates="risk_settings")


class Alert(Base):
    __tablename__ = "alerts"

    __table_args__ = (
        Index("ix_alerts_strategy_time", "strategy_id", "received_at"),
        Index("ix_alerts_symbol_time", "symbol", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    strategy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )

    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(64))
    interval: Mapped[Optional[str]] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Optional[float]] = mapped_column(Float)
    price: Mapped[Optional[float]] = mapped_column(Float)

    platform: Mapped[str] = mapped_column(
        String(32), nullable=False, default="TRADINGVIEW"
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="TRADINGVIEW"
    )

    rule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("indicator_rules.id", ondelete="SET NULL"), nullable=True
    )

    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text())

    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    bar_time: Mapped[Optional[datetime]] = mapped_column(DateTime)

    strategy: Mapped[Optional[Strategy]] = relationship(back_populates="alerts")
    orders: Mapped[List["Order"]] = relationship(back_populates="alert")
    rule: Mapped[Optional["IndicatorRule"]] = relationship(back_populates="alerts")


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        Index("ix_orders_strategy_status", "strategy_id", "status"),
        Index("ix_orders_symbol_time", "symbol", "created_at"),
        Index("ix_orders_synthetic_status", "synthetic_gtt", "status"),
        Index("ix_orders_portfolio_group_id", "portfolio_group_id"),
        Index(
            "ix_orders_broker_name_order_id",
            "broker_name",
            "broker_order_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    alert_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    strategy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )
    # Optional portfolio attribution for orders created via portfolio workflows.
    portfolio_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
    )

    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(64))

    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MARKET"
    )
    trigger_price: Mapped[Optional[float]] = mapped_column(Float)
    trigger_percent: Mapped[Optional[float]] = mapped_column(Float)
    product: Mapped[str] = mapped_column(String(16), nullable=False, default="MIS")
    gtt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    synthetic_gtt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trigger_operator: Mapped[Optional[str]] = mapped_column(String(2))
    armed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_seen_price: Mapped[Optional[float]] = mapped_column(Float)
    triggered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="WAITING")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="MANUAL")
    execution_target: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LIVE"
    )

    broker_name: Mapped[str] = mapped_column(
        String(32), nullable=False, default="zerodha"
    )
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64))

    zerodha_order_id: Mapped[Optional[str]] = mapped_column(String(64))
    broker_account_id: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text())
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    alert: Mapped[Optional[Alert]] = relationship(back_populates="orders")
    strategy: Mapped[Optional[Strategy]] = relationship(back_populates="orders")


class IndicatorRule(Base):
    __tablename__ = "indicator_rules"

    __table_args__ = (
        Index("ix_indicator_rules_user_symbol", "user_id", "symbol"),
        Index("ix_indicator_rules_user_timeframe", "user_id", "timeframe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
    )

    name: Mapped[Optional[str]] = mapped_column(String(255))
    symbol: Mapped[Optional[str]] = mapped_column(String(128))
    universe: Mapped[Optional[str]] = mapped_column(String(32))
    exchange: Mapped[Optional[str]] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="1d")

    logic: Mapped[str] = mapped_column(String(8), nullable=False, default="AND")
    conditions_json: Mapped[str] = mapped_column(Text, nullable=False)
    expression_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dsl_expression: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Future-friendly target fields, in addition to the existing
    # symbol/universe/exchange columns. For now these are mostly used for
    # planning and can remain NULL for existing rules.
    target_type: Mapped[Optional[str]] = mapped_column(String(16))
    target_id: Mapped[Optional[str]] = mapped_column(String(128))

    trigger_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ONCE",
    )
    action_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ALERT_ONLY",
    )
    action_params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    strategy: Mapped[Optional[Strategy]] = relationship()
    alerts: Mapped[List[Alert]] = relationship(back_populates="rule")


class Position(Base):
    __tablename__ = "positions"

    __table_args__ = (
        UniqueConstraint(
            "broker_name",
            "symbol",
            "exchange",
            "product",
            name="ux_positions_broker_symbol_exchange_product",
        ),
        Index("ix_positions_broker_symbol", "broker_name", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_name: Mapped[str] = mapped_column(
        String(32), nullable=False, default="zerodha"
    )
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, default="NSE")
    product: Mapped[str] = mapped_column(String(16), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_updated: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "broker_name",
            "as_of_date",
            "symbol",
            "exchange",
            "product",
            name="ux_position_snapshots_broker_date_symbol_exchange_product",
        ),
        Index(
            "ix_position_snapshots_broker_date_symbol",
            "broker_name",
            "as_of_date",
            "symbol",
        ),
        Index(
            "ix_position_snapshots_broker_symbol_date",
            "broker_name",
            "symbol",
            "as_of_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_name: Mapped[str] = mapped_column(
        String(32), nullable=False, default="zerodha"
    )
    as_of_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )

    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, default="NSE")
    product: Mapped[str] = mapped_column(String(16), nullable=False)

    qty: Mapped[float] = mapped_column(Float, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    last_price: Mapped[Optional[float]] = mapped_column(Float)
    close_price: Mapped[Optional[float]] = mapped_column(Float)
    value: Mapped[Optional[float]] = mapped_column(Float)
    m2m: Mapped[Optional[float]] = mapped_column(Float)
    unrealised: Mapped[Optional[float]] = mapped_column(Float)
    realised: Mapped[Optional[float]] = mapped_column(Float)

    buy_qty: Mapped[Optional[float]] = mapped_column(Float)
    buy_avg_price: Mapped[Optional[float]] = mapped_column(Float)
    sell_qty: Mapped[Optional[float]] = mapped_column(Float)
    sell_avg_price: Mapped[Optional[float]] = mapped_column(Float)

    day_buy_qty: Mapped[Optional[float]] = mapped_column(Float)
    day_buy_avg_price: Mapped[Optional[float]] = mapped_column(Float)
    day_sell_qty: Mapped[Optional[float]] = mapped_column(Float)
    day_sell_avg_price: Mapped[Optional[float]] = mapped_column(Float)

    holding_qty: Mapped[Optional[float]] = mapped_column(Float)


class AnalyticsTrade(Base):
    __tablename__ = "analytics_trades"

    __table_args__ = (
        Index(
            "ix_analytics_trades_strategy_closed_at",
            "strategy_id",
            "closed_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    exit_order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )

    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    r_multiple: Mapped[Optional[float]] = mapped_column(Float)

    opened_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


__all__ = [
    "Strategy",
    "RiskSettings",
    "Alert",
    "Order",
    "Position",
    "PositionSnapshot",
    "AnalyticsTrade",
]
