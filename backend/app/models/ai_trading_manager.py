from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class AiTmTradePlan(Base):
    __tablename__ = "ai_tm_trade_plans"

    __table_args__ = (
        UniqueConstraint("plan_id", name="ux_ai_tm_trade_plans_plan_id"),
        Index("ix_ai_tm_trade_plans_account_ts", "account_id", "created_at"),
        Index("ix_ai_tm_trade_plans_user_ts", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    plan_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class AiTmPlaybook(Base):
    __tablename__ = "ai_tm_playbooks"

    __table_args__ = (
        UniqueConstraint("playbook_id", name="ux_ai_tm_playbooks_playbook_id"),
        Index("ix_ai_tm_playbooks_account_id", "account_id"),
        Index("ix_ai_tm_playbooks_user_id", "user_id"),
        Index("ix_ai_tm_playbooks_next_run", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playbook_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text())
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    armed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    armed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    armed_by_message_id: Mapped[Optional[str]] = mapped_column(String(64))
    cadence_sec: Mapped[Optional[int]] = mapped_column(Integer)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AiTmPlaybookRun(Base):
    __tablename__ = "ai_tm_playbook_runs"

    __table_args__ = (
        UniqueConstraint("run_id", name="ux_ai_tm_playbook_runs_run_id"),
        UniqueConstraint("playbook_id", "dedupe_key", name="ux_ai_tm_playbook_runs_dedupe"),
        Index("ix_ai_tm_playbook_runs_playbook_ts", "playbook_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    playbook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_tm_playbooks.playbook_id", ondelete="CASCADE"), nullable=False
    )
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_id: Mapped[Optional[str]] = mapped_column(String(64))
    authorization_message_id: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="STARTED")  # STARTED/COMPLETED/FAILED
    outcome_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class AiTmExpectedPosition(Base):
    __tablename__ = "ai_tm_expected_positions"

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", "product", name="ux_ai_tm_expected_pos_key"),
        Index("ix_ai_tm_expected_positions_account", "account_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    product: Mapped[str] = mapped_column(String(16), nullable=False, default="CNC")
    expected_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_price: Mapped[Optional[float]] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AiTmBrokerSnapshot(Base):
    __tablename__ = "ai_tm_broker_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "as_of_ts",
            "source",
            name="ux_ai_tm_broker_snapshot_key",
        ),
        Index("ix_ai_tm_broker_snapshots_user_ts", "user_id", "as_of_ts"),
        Index("ix_ai_tm_broker_snapshots_account_ts", "account_id", "as_of_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    as_of_ts: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="stub")
    payload_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class AiTmLedgerSnapshot(Base):
    __tablename__ = "ai_tm_ledger_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "as_of_ts",
            name="ux_ai_tm_ledger_snapshot_key",
        ),
        Index("ix_ai_tm_ledger_snapshots_user_ts", "user_id", "as_of_ts"),
        Index("ix_ai_tm_ledger_snapshots_account_ts", "account_id", "as_of_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    as_of_ts: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class AiTmDecisionTrace(Base):
    __tablename__ = "ai_tm_decision_traces"

    __table_args__ = (
        UniqueConstraint("decision_id", name="ux_ai_tm_decision_traces_decision_id"),
        Index("ix_ai_tm_decision_traces_user_ts", "user_id", "created_at"),
        Index("ix_ai_tm_decision_traces_account_ts", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    user_message: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    inputs_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    tools_json: Mapped[str] = mapped_column(Text(), nullable=False, default="[]")
    riskgate_json: Mapped[Optional[str]] = mapped_column(Text())
    outcome_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    explanations_json: Mapped[str] = mapped_column(Text(), nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class AiTmChatMessage(Base):
    __tablename__ = "ai_tm_chat_messages"

    __table_args__ = (
        Index("ix_ai_tm_chat_messages_user_ts", "user_id", "created_at"),
        Index("ix_ai_tm_chat_messages_account_ts", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user/assistant/system
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64))
    decision_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class AiTmFile(Base):
    __tablename__ = "ai_tm_files"

    __table_args__ = (
        UniqueConstraint("file_id", name="ux_ai_tm_files_file_id"),
        Index("ix_ai_tm_files_user_ts", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(Text(), nullable=False)
    summary_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AiTmIdempotencyRecord(Base):
    __tablename__ = "ai_tm_idempotency_records"

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="ux_ai_tm_idempotency_key",
        ),
        Index("ix_ai_tm_idempotency_user_ts", "user_id", "first_seen_at"),
        Index("ix_ai_tm_idempotency_account_ts", "account_id", "first_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="STARTED")
    result_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    first_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AiTmMonitorJob(Base):
    __tablename__ = "ai_tm_monitor_jobs"

    __table_args__ = (
        UniqueConstraint("monitor_job_id", name="ux_ai_tm_monitor_job_id"),
        Index("ix_ai_tm_monitor_jobs_user_id", "user_id"),
        Index("ix_ai_tm_monitor_jobs_account_id", "account_id"),
        Index("ix_ai_tm_monitor_jobs_next_run", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cadence_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    job_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    next_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AiTmMonitorTrigger(Base):
    __tablename__ = "ai_tm_monitor_triggers"

    __table_args__ = (
        UniqueConstraint(
            "monitor_job_id",
            "dedupe_key",
            name="ux_ai_tm_monitor_trigger_dedupe",
        ),
        Index("ix_ai_tm_monitor_triggers_job_ts", "monitor_job_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_tm_monitor_jobs.monitor_job_id", ondelete="CASCADE"), nullable=False
    )
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class AiTmReconciliationRun(Base):
    __tablename__ = "ai_tm_reconciliation_runs"

    __table_args__ = (
        UniqueConstraint("run_id", name="ux_ai_tm_reconciliation_run_id"),
        Index("ix_ai_tm_reconciliation_runs_user_ts", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    broker_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_tm_broker_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    ledger_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_tm_ledger_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    deltas_json: Mapped[str] = mapped_column(Text(), nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class AiTmException(Base):
    __tablename__ = "ai_tm_exceptions"

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "exception_type",
            "key",
            "status",
            name="ux_ai_tm_exceptions_dedupe",
        ),
        Index("ix_ai_tm_exceptions_user_status", "user_id", "status"),
        Index("ix_ai_tm_exceptions_account_status", "account_id", "status"),
        Index("ix_ai_tm_exceptions_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exception_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    exception_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(1), nullable=False, default="M")  # L/M/H
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    details_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")  # OPEN/ACK
    related_decision_id: Mapped[Optional[str]] = mapped_column(String(64))
    related_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = [
    "AiTmBrokerSnapshot",
    "AiTmChatMessage",
    "AiTmDecisionTrace",
    "AiTmException",
    "AiTmIdempotencyRecord",
    "AiTmLedgerSnapshot",
    "AiTmMonitorJob",
    "AiTmMonitorTrigger",
    "AiTmPlaybook",
    "AiTmPlaybookRun",
    "AiTmReconciliationRun",
    "AiTmTradePlan",
    "AiTmExpectedPosition",
]
