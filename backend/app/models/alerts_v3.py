from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertDefinition(Base):
    __tablename__ = "alert_definitions"

    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('SYMBOL', 'HOLDINGS', 'GROUP')",
            name="ck_alert_definitions_target_kind",
        ),
        CheckConstraint(
            "action_type IN ('ALERT_ONLY', 'BUY', 'SELL')",
            name="ck_alert_definitions_action_type",
        ),
        CheckConstraint(
            "trigger_mode IN ('ONCE', 'ONCE_PER_BAR', 'EVERY_TIME')",
            name="ck_alert_definitions_trigger_mode",
        ),
        Index("ix_alert_definitions_user_enabled", "user_id", "enabled"),
        Index(
            "ix_alert_definitions_user_target", "user_id", "target_kind", "target_ref"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Targeting
    # - SYMBOL: target_ref is the symbol (exchange optional)
    # - HOLDINGS: target_ref is 'ZERODHA' (reserved) for now
    # - GROUP: target_ref is group_id (string)
    target_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SYMBOL"
    )
    target_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(32))

    # Evaluation cadence for this alert (e.g. 1m/5m/1h/1d).
    evaluation_cadence: Mapped[str] = mapped_column(
        String(8), nullable=False, default="1m"
    )

    # Condition / expression
    variables_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    condition_dsl: Mapped[str] = mapped_column(Text, nullable=False)
    condition_ast_json: Mapped[Optional[str]] = mapped_column(Text)

    # Action behavior (Phase B): optional trade template attached to the alert.
    action_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ALERT_ONLY"
    )
    action_params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Trigger behavior
    trigger_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ONCE_PER_BAR"
    )
    throttle_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    only_market_hours: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Lifecycle
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Bookkeeping
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class CustomIndicator(Base):
    __tablename__ = "custom_indicators"

    __table_args__ = (
        Index("ix_custom_indicators_user_enabled", "user_id", "enabled"),
        UniqueConstraint("user_id", "name", name="ux_custom_indicators_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    body_dsl: Mapped[str] = mapped_column(Text, nullable=False)
    body_ast_json: Mapped[Optional[str]] = mapped_column(Text)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    __table_args__ = (
        Index("ix_alert_events_alert_time", "alert_definition_id", "triggered_at"),
        Index("ix_alert_events_symbol_time", "symbol", "triggered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_definition_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alert_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(64))

    evaluation_cadence: Mapped[Optional[str]] = mapped_column(String(8))
    reason: Mapped[Optional[str]] = mapped_column(Text())
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    bar_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


__all__ = ["AlertDefinition", "AlertEvent", "CustomIndicator"]
