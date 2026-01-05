from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class StrategyDeployment(Base):
    __tablename__ = "strategy_deployments"

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "name",
            name="ux_strategy_deployments_owner_name",
        ),
        CheckConstraint(
            "kind IN ('STRATEGY', 'PORTFOLIO_STRATEGY')",
            name="ck_strategy_deployments_kind",
        ),
        CheckConstraint(
            "execution_target IN ('PAPER', 'LIVE')",
            name="ck_strategy_deployments_execution_target",
        ),
        CheckConstraint(
            "target_kind IN ('SYMBOL', 'GROUP')",
            name="ck_strategy_deployments_target_kind",
        ),
        CheckConstraint(
            "timeframe IN ('1m','5m','15m','30m','1h','1d')",
            name="ck_strategy_deployments_timeframe",
        ),
        CheckConstraint(
            "(target_kind = 'SYMBOL' AND symbol IS NOT NULL) OR "
            "(target_kind = 'GROUP' AND group_id IS NOT NULL)",
            name="ck_strategy_deployments_target_fields",
        ),
        Index("ix_strategy_deployments_owner_id", "owner_id"),
        Index("ix_strategy_deployments_kind", "kind"),
        Index("ix_strategy_deployments_enabled", "enabled"),
        Index("ix_strategy_deployments_execution_target", "execution_target"),
        Index("ix_strategy_deployments_broker_name", "broker_name"),
        Index("ix_strategy_deployments_group_id", "group_id"),
        Index("ix_strategy_deployments_symbol", "exchange", "symbol"),
        Index("ix_strategy_deployments_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text())

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_target: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PAPER",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    broker_name: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="zerodha",
    )
    product: Mapped[str] = mapped_column(String(16), nullable=False, default="CNC")

    target_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="SYMBOL",
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True,
    )
    exchange: Mapped[Optional[str]] = mapped_column(String(32))
    symbol: Mapped[Optional[str]] = mapped_column(String(128))

    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="1d")

    config_json: Mapped[str] = mapped_column(Text(), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    state: Mapped["StrategyDeploymentState"] = relationship(
        back_populates="deployment",
        uselist=False,
        cascade="all,delete-orphan",
        passive_deletes=True,
    )


class StrategyDeploymentState(Base):
    __tablename__ = "strategy_deployment_states"

    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            name="ux_strategy_deployment_states_deployment_id",
        ),
        CheckConstraint(
            "status IN ('STOPPED', 'RUNNING', 'PAUSED', 'ERROR')",
            name="ck_strategy_deployment_states_status",
        ),
        Index("ix_strategy_deployment_states_deployment_id", "deployment_id"),
        Index("ix_strategy_deployment_states_status", "status"),
        Index(
            "ix_strategy_deployment_states_last_evaluated_at",
            "last_evaluated_at",
        ),
        Index("ix_strategy_deployment_states_next_evaluate_at", "next_evaluate_at"),
        Index("ix_strategy_deployment_states_last_eval_at", "last_eval_at"),
        Index("ix_strategy_deployment_states_next_eval_at", "next_eval_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="STOPPED")

    state_json: Mapped[Optional[str]] = mapped_column(Text())
    exposure_json: Mapped[Optional[str]] = mapped_column(Text())

    # v2 legacy (kept for backwards compatibility with existing APIs/UI)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    next_evaluate_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    # v3 heartbeat fields (sec 12)
    last_eval_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_eval_bar_end_ts: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    runtime_state: Mapped[Optional[str]] = mapped_column(String(32))
    last_decision: Mapped[Optional[str]] = mapped_column(String(32))
    last_decision_reason: Mapped[Optional[str]] = mapped_column(String(255))
    next_eval_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    last_error: Mapped[Optional[str]] = mapped_column(Text())

    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    stopped_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    paused_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    resumed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    pause_reason: Mapped[Optional[str]] = mapped_column(String(255))

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    deployment: Mapped[StrategyDeployment] = relationship(back_populates="state")


__all__ = ["StrategyDeployment", "StrategyDeploymentState"]
