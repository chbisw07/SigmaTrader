"""Add strategy deployment scheduler/job queue tables.

Revision ID: 0046
Revises: 0045_add_strategy_deployments
Create Date: 2026-01-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045_add_strategy_deployments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "strategy_deployment_jobs" not in tables:
        op.create_table(
            "strategy_deployment_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "deployment_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("scheduled_for", sa.DateTime(timezone=True)),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("run_after", sa.DateTime(timezone=True)),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("locked_by", sa.String(length=64)),
            sa.Column("locked_at", sa.DateTime(timezone=True)),
            sa.Column("last_error", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')",
                name="ck_strategy_deployment_jobs_status",
            ),
            sa.CheckConstraint(
                "kind IN ('BAR_CLOSED', 'DAILY_PROXY_CLOSED', 'WINDOW')",
                name="ck_strategy_deployment_jobs_kind",
            ),
            sa.UniqueConstraint(
                "dedupe_key",
                name="ux_strategy_deployment_jobs_dedupe_key",
            ),
        )
        inspector = sa.inspect(bind)

    existing_idx = {
        i.get("name") for i in inspector.get_indexes("strategy_deployment_jobs")
    }
    for name, cols in [
        ("ix_strategy_deployment_jobs_deployment_id", ["deployment_id"]),
        ("ix_strategy_deployment_jobs_owner_id", ["owner_id"]),
        ("ix_strategy_deployment_jobs_status", ["status"]),
        ("ix_strategy_deployment_jobs_run_after", ["run_after"]),
        ("ix_strategy_deployment_jobs_created_at", ["created_at"]),
        ("ix_strategy_deployment_jobs_locked_at", ["locked_at"]),
    ]:
        if name not in existing_idx:
            op.create_index(name, "strategy_deployment_jobs", cols)

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "strategy_deployment_locks" not in tables:
        op.create_table(
            "strategy_deployment_locks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "deployment_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("locked_by", sa.String(length=64)),
            sa.Column("locked_until", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "deployment_id",
                name="ux_strategy_deployment_locks_deployment_id",
            ),
        )
        inspector = sa.inspect(bind)

    existing_idx = {
        i.get("name") for i in inspector.get_indexes("strategy_deployment_locks")
    }
    for name, cols in [
        ("ix_strategy_deployment_locks_deployment_id", ["deployment_id"]),
        ("ix_strategy_deployment_locks_locked_until", ["locked_until"]),
    ]:
        if name not in existing_idx:
            op.create_index(name, "strategy_deployment_locks", cols)

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "strategy_deployment_bar_cursors" not in tables:
        op.create_table(
            "strategy_deployment_bar_cursors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "deployment_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("exchange", sa.String(length=32), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("last_emitted_bar_end_ts", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "timeframe IN ('1m','5m','15m','30m','1h')",
                name="ck_strategy_deployment_bar_cursors_timeframe",
            ),
            sa.UniqueConstraint(
                "deployment_id",
                "exchange",
                "symbol",
                "timeframe",
                name="ux_strategy_deployment_bar_cursors_dep_symbol_tf",
            ),
        )
        inspector = sa.inspect(bind)

    existing_idx = {
        i.get("name") for i in inspector.get_indexes("strategy_deployment_bar_cursors")
    }
    for name, cols in [
        ("ix_strategy_deployment_bar_cursors_deployment_id", ["deployment_id"]),
        (
            "ix_strategy_deployment_bar_cursors_symbol_tf",
            ["exchange", "symbol", "timeframe"],
        ),
    ]:
        if name not in existing_idx:
            op.create_index(name, "strategy_deployment_bar_cursors", cols)

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "strategy_deployment_actions" not in tables:
        op.create_table(
            "strategy_deployment_actions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "deployment_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "job_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployment_jobs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "kind",
                sa.String(length=32),
                nullable=False,
                server_default="JOB_EXECUTED",
            ),
            sa.Column("payload_json", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)

    existing_idx = {
        i.get("name") for i in inspector.get_indexes("strategy_deployment_actions")
    }
    for name, cols in [
        ("ix_strategy_deployment_actions_deployment_id", ["deployment_id"]),
        ("ix_strategy_deployment_actions_created_at", ["created_at"]),
        ("ix_strategy_deployment_actions_kind", ["kind"]),
    ]:
        if name not in existing_idx:
            op.create_index(name, "strategy_deployment_actions", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "strategy_deployment_actions" in tables:
        existing = {
            i.get("name") for i in inspector.get_indexes("strategy_deployment_actions")
        }
        for name in [
            "ix_strategy_deployment_actions_kind",
            "ix_strategy_deployment_actions_created_at",
            "ix_strategy_deployment_actions_deployment_id",
        ]:
            if name in existing:
                op.drop_index(name, table_name="strategy_deployment_actions")
        op.drop_table("strategy_deployment_actions")

    inspector = sa.inspect(bind)
    if "strategy_deployment_bar_cursors" in inspector.get_table_names():
        existing = {
            i.get("name")
            for i in inspector.get_indexes("strategy_deployment_bar_cursors")
        }
        for name in [
            "ix_strategy_deployment_bar_cursors_symbol_tf",
            "ix_strategy_deployment_bar_cursors_deployment_id",
        ]:
            if name in existing:
                op.drop_index(name, table_name="strategy_deployment_bar_cursors")
        op.drop_table("strategy_deployment_bar_cursors")

    inspector = sa.inspect(bind)
    if "strategy_deployment_locks" in inspector.get_table_names():
        existing = {
            i.get("name") for i in inspector.get_indexes("strategy_deployment_locks")
        }
        for name in [
            "ix_strategy_deployment_locks_locked_until",
            "ix_strategy_deployment_locks_deployment_id",
        ]:
            if name in existing:
                op.drop_index(name, table_name="strategy_deployment_locks")
        op.drop_table("strategy_deployment_locks")

    inspector = sa.inspect(bind)
    if "strategy_deployment_jobs" in inspector.get_table_names():
        existing = {
            i.get("name") for i in inspector.get_indexes("strategy_deployment_jobs")
        }
        for name in [
            "ix_strategy_deployment_jobs_locked_at",
            "ix_strategy_deployment_jobs_created_at",
            "ix_strategy_deployment_jobs_run_after",
            "ix_strategy_deployment_jobs_status",
            "ix_strategy_deployment_jobs_owner_id",
            "ix_strategy_deployment_jobs_deployment_id",
        ]:
            if name in existing:
                op.drop_index(name, table_name="strategy_deployment_jobs")
        op.drop_table("strategy_deployment_jobs")
