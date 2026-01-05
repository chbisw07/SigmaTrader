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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class StrategyDeploymentJob(Base):
    __tablename__ = "strategy_deployment_jobs"

    __table_args__ = (
        UniqueConstraint(
            "dedupe_key",
            name="ux_strategy_deployment_jobs_dedupe_key",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')",
            name="ck_strategy_deployment_jobs_status",
        ),
        CheckConstraint(
            "kind IN ('BAR_CLOSED', 'DAILY_PROXY_CLOSED', 'WINDOW')",
            name="ck_strategy_deployment_jobs_kind",
        ),
        Index("ix_strategy_deployment_jobs_deployment_id", "deployment_id"),
        Index("ix_strategy_deployment_jobs_owner_id", "owner_id"),
        Index("ix_strategy_deployment_jobs_status", "status"),
        Index("ix_strategy_deployment_jobs_run_after", "run_after"),
        Index("ix_strategy_deployment_jobs_created_at", "created_at"),
        Index("ix_strategy_deployment_jobs_locked_at", "locked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)

    scheduled_for: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    payload_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")

    run_after: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    locked_by: Mapped[Optional[str]] = mapped_column(String(64))
    locked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_error: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class StrategyDeploymentLock(Base):
    __tablename__ = "strategy_deployment_locks"

    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            name="ux_strategy_deployment_locks_deployment_id",
        ),
        Index("ix_strategy_deployment_locks_deployment_id", "deployment_id"),
        Index("ix_strategy_deployment_locks_locked_until", "locked_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )

    locked_by: Mapped[Optional[str]] = mapped_column(String(64))
    locked_until: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class StrategyDeploymentBarCursor(Base):
    __tablename__ = "strategy_deployment_bar_cursors"

    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "exchange",
            "symbol",
            "timeframe",
            name="ux_strategy_deployment_bar_cursors_dep_symbol_tf",
        ),
        CheckConstraint(
            "timeframe IN ('1m','5m','15m','30m','1h')",
            name="ck_strategy_deployment_bar_cursors_timeframe",
        ),
        Index("ix_strategy_deployment_bar_cursors_deployment_id", "deployment_id"),
        Index(
            "ix_strategy_deployment_bar_cursors_symbol_tf",
            "exchange",
            "symbol",
            "timeframe",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)

    last_emitted_bar_end_ts: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class StrategyDeploymentAction(Base):
    __tablename__ = "strategy_deployment_actions"

    __table_args__ = (
        Index("ix_strategy_deployment_actions_deployment_id", "deployment_id"),
        Index("ix_strategy_deployment_actions_created_at", "created_at"),
        Index("ix_strategy_deployment_actions_kind", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("strategy_deployment_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="JOB_EXECUTED",
    )
    payload_json: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class StrategyDeploymentEventLog(Base):
    __tablename__ = "strategy_deployment_event_logs"

    __table_args__ = (
        Index("ix_strategy_deployment_event_logs_deployment_id", "deployment_id"),
        Index("ix_strategy_deployment_event_logs_created_at", "created_at"),
        Index("ix_strategy_deployment_event_logs_kind", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("strategy_deployment_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


__all__ = [
    "StrategyDeploymentAction",
    "StrategyDeploymentBarCursor",
    "StrategyDeploymentEventLog",
    "StrategyDeploymentJob",
    "StrategyDeploymentLock",
]
