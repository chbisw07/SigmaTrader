"""Add AI Trading Manager Phase 0 tables.

Revision ID: 0071
Revises: 0070
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_tm_broker_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("as_of_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="stub"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "as_of_ts",
            "source",
            name="ux_ai_tm_broker_snapshot_key",
        ),
    )
    op.create_index(
        "ix_ai_tm_broker_snapshots_user_ts",
        "ai_tm_broker_snapshots",
        ["user_id", "as_of_ts"],
    )
    op.create_index(
        "ix_ai_tm_broker_snapshots_account_ts",
        "ai_tm_broker_snapshots",
        ["account_id", "as_of_ts"],
    )

    op.create_table(
        "ai_tm_ledger_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("as_of_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "as_of_ts",
            name="ux_ai_tm_ledger_snapshot_key",
        ),
    )
    op.create_index(
        "ix_ai_tm_ledger_snapshots_user_ts",
        "ai_tm_ledger_snapshots",
        ["user_id", "as_of_ts"],
    )
    op.create_index(
        "ix_ai_tm_ledger_snapshots_account_ts",
        "ai_tm_ledger_snapshots",
        ["account_id", "as_of_ts"],
    )

    op.create_table(
        "ai_tm_decision_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("user_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("inputs_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("tools_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("riskgate_json", sa.Text(), nullable=True),
        sa.Column("outcome_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("explanations_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("decision_id", name="ux_ai_tm_decision_traces_decision_id"),
    )
    op.create_index(
        "ix_ai_tm_decision_traces_user_ts",
        "ai_tm_decision_traces",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_tm_decision_traces_account_ts",
        "ai_tm_decision_traces",
        ["account_id", "created_at"],
    )

    op.create_table(
        "ai_tm_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("thread_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("decision_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_tm_chat_messages_user_ts",
        "ai_tm_chat_messages",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_tm_chat_messages_account_ts",
        "ai_tm_chat_messages",
        ["account_id", "created_at"],
    )

    op.create_table(
        "ai_tm_idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="STARTED"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="ux_ai_tm_idempotency_key",
        ),
    )
    op.create_index(
        "ix_ai_tm_idempotency_user_ts",
        "ai_tm_idempotency_records",
        ["user_id", "first_seen_at"],
    )
    op.create_index(
        "ix_ai_tm_idempotency_account_ts",
        "ai_tm_idempotency_records",
        ["account_id", "first_seen_at"],
    )

    op.create_table(
        "ai_tm_monitor_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("monitor_job_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("cadence_sec", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("job_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("monitor_job_id", name="ux_ai_tm_monitor_job_id"),
    )
    op.create_index("ix_ai_tm_monitor_jobs_user_id", "ai_tm_monitor_jobs", ["user_id"])
    op.create_index(
        "ix_ai_tm_monitor_jobs_account_id",
        "ai_tm_monitor_jobs",
        ["account_id"],
    )
    op.create_index(
        "ix_ai_tm_monitor_jobs_next_run",
        "ai_tm_monitor_jobs",
        ["next_run_at"],
    )

    op.create_table(
        "ai_tm_monitor_triggers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "monitor_job_id",
            sa.String(length=64),
            sa.ForeignKey("ai_tm_monitor_jobs.monitor_job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("trigger_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "monitor_job_id",
            "dedupe_key",
            name="ux_ai_tm_monitor_trigger_dedupe",
        ),
    )
    op.create_index(
        "ix_ai_tm_monitor_triggers_job_ts",
        "ai_tm_monitor_triggers",
        ["monitor_job_id", "created_at"],
    )

    op.create_table(
        "ai_tm_reconciliation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column(
            "broker_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("ai_tm_broker_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ledger_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("ai_tm_ledger_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("deltas_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", name="ux_ai_tm_reconciliation_run_id"),
    )
    op.create_index(
        "ix_ai_tm_reconciliation_runs_user_ts",
        "ai_tm_reconciliation_runs",
        ["user_id", "created_at"],
    )

    op.create_table(
        "ai_tm_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exception_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("exception_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=1), nullable=False, server_default="M"),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("details_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("related_decision_id", sa.String(length=64), nullable=True),
        sa.Column("related_run_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "exception_type",
            "key",
            "status",
            name="ux_ai_tm_exceptions_dedupe",
        ),
    )
    op.create_index(
        "ix_ai_tm_exceptions_user_status",
        "ai_tm_exceptions",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_ai_tm_exceptions_account_status",
        "ai_tm_exceptions",
        ["account_id", "status"],
    )
    op.create_index(
        "ix_ai_tm_exceptions_severity",
        "ai_tm_exceptions",
        ["severity"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tm_exceptions_severity", table_name="ai_tm_exceptions")
    op.drop_index("ix_ai_tm_exceptions_account_status", table_name="ai_tm_exceptions")
    op.drop_index("ix_ai_tm_exceptions_user_status", table_name="ai_tm_exceptions")
    op.drop_table("ai_tm_exceptions")

    op.drop_index(
        "ix_ai_tm_reconciliation_runs_user_ts",
        table_name="ai_tm_reconciliation_runs",
    )
    op.drop_table("ai_tm_reconciliation_runs")

    op.drop_index(
        "ix_ai_tm_monitor_triggers_job_ts",
        table_name="ai_tm_monitor_triggers",
    )
    op.drop_table("ai_tm_monitor_triggers")

    op.drop_index("ix_ai_tm_monitor_jobs_next_run", table_name="ai_tm_monitor_jobs")
    op.drop_index("ix_ai_tm_monitor_jobs_account_id", table_name="ai_tm_monitor_jobs")
    op.drop_index("ix_ai_tm_monitor_jobs_user_id", table_name="ai_tm_monitor_jobs")
    op.drop_table("ai_tm_monitor_jobs")

    op.drop_index(
        "ix_ai_tm_idempotency_account_ts",
        table_name="ai_tm_idempotency_records",
    )
    op.drop_index(
        "ix_ai_tm_idempotency_user_ts",
        table_name="ai_tm_idempotency_records",
    )
    op.drop_table("ai_tm_idempotency_records")

    op.drop_index(
        "ix_ai_tm_chat_messages_account_ts",
        table_name="ai_tm_chat_messages",
    )
    op.drop_index(
        "ix_ai_tm_chat_messages_user_ts",
        table_name="ai_tm_chat_messages",
    )
    op.drop_table("ai_tm_chat_messages")

    op.drop_index(
        "ix_ai_tm_decision_traces_account_ts",
        table_name="ai_tm_decision_traces",
    )
    op.drop_index(
        "ix_ai_tm_decision_traces_user_ts",
        table_name="ai_tm_decision_traces",
    )
    op.drop_table("ai_tm_decision_traces")

    op.drop_index(
        "ix_ai_tm_ledger_snapshots_account_ts",
        table_name="ai_tm_ledger_snapshots",
    )
    op.drop_index(
        "ix_ai_tm_ledger_snapshots_user_ts",
        table_name="ai_tm_ledger_snapshots",
    )
    op.drop_table("ai_tm_ledger_snapshots")

    op.drop_index(
        "ix_ai_tm_broker_snapshots_account_ts",
        table_name="ai_tm_broker_snapshots",
    )
    op.drop_index(
        "ix_ai_tm_broker_snapshots_user_ts",
        table_name="ai_tm_broker_snapshots",
    )
    op.drop_table("ai_tm_broker_snapshots")
