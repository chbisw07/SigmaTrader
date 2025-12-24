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


class SignalStrategy(Base):
    """A reusable, user-facing saved strategy for DSL V3 (signals + overlays).

    Strategy logic is stored in version rows (`SignalStrategyVersion`) so we can
    pin consumers (alerts/screener/dashboard) to a specific version.
    """

    __tablename__ = "signal_strategies"

    __table_args__ = (
        CheckConstraint(
            "scope IN ('USER', 'GLOBAL')",
            name="ck_signal_strategies_scope",
        ),
        UniqueConstraint("scope", "owner_id", "name", name="ux_signal_strategies_name"),
        Index("ix_signal_strategies_owner_updated", "owner_id", "updated_at"),
        Index("ix_signal_strategies_scope_updated", "scope", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Ownership and sharing
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="USER")
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text())

    # Freeform tags/regimes are stored at the strategy level so they apply
    # to all versions.
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    regimes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Bookkeeping
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SignalStrategyVersion(Base):
    __tablename__ = "signal_strategy_versions"

    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "version",
            name="ux_signal_strategy_versions_strategy_version",
        ),
        Index("ix_signal_strategy_versions_strategy", "strategy_id", "version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("signal_strategies.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Inputs (parameters) schema, e.g.
    # [{"name":"RSI_LEN","type":"number","default":14}, ...]
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Shared variables for this strategy version
    # (same shape as alerts_v3 variables_json).
    variables_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Outputs: list of named outputs (signals + overlays).
    # Example:
    # [{"name":"entry","kind":"SIGNAL","dsl":"RSI(close,14,1d) < 30"},
    #  {"name":"rsi","kind":"OVERLAY","dsl":"RSI(close,14,1d)"}]
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Derived compatibility metadata for UI filtering.
    # Example: {"requires_holdings_metrics": false}
    compatibility_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )


__all__ = ["SignalStrategy", "SignalStrategyVersion"]
