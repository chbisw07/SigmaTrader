"""Add AI TM playbooks + expected ledger tables.

Revision ID: 0072
Revises: 0071
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_tm_trade_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("plan_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("plan_id", name="ux_ai_tm_trade_plans_plan_id"),
    )
    op.create_index("ix_ai_tm_trade_plans_account_ts", "ai_tm_trade_plans", ["account_id", "created_at"])
    op.create_index("ix_ai_tm_trade_plans_user_ts", "ai_tm_trade_plans", ["user_id", "created_at"])

    op.create_table(
        "ai_tm_playbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("playbook_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("armed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("armed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cadence_sec", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("playbook_id", name="ux_ai_tm_playbooks_playbook_id"),
    )
    op.create_index("ix_ai_tm_playbooks_account_id", "ai_tm_playbooks", ["account_id"])
    op.create_index("ix_ai_tm_playbooks_user_id", "ai_tm_playbooks", ["user_id"])
    op.create_index("ix_ai_tm_playbooks_next_run", "ai_tm_playbooks", ["next_run_at"])

    op.create_table(
        "ai_tm_playbook_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column(
            "playbook_id",
            sa.String(length=64),
            sa.ForeignKey("ai_tm_playbooks.playbook_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="STARTED"),
        sa.Column("outcome_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", name="ux_ai_tm_playbook_runs_run_id"),
        sa.UniqueConstraint("playbook_id", "dedupe_key", name="ux_ai_tm_playbook_runs_dedupe"),
    )
    op.create_index("ix_ai_tm_playbook_runs_playbook_ts", "ai_tm_playbook_runs", ["playbook_id", "started_at"])

    op.create_table(
        "ai_tm_expected_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("product", sa.String(length=16), nullable=False, server_default="CNC"),
        sa.Column("expected_qty", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_price", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "symbol", "product", name="ux_ai_tm_expected_pos_key"),
    )
    op.create_index("ix_ai_tm_expected_positions_account", "ai_tm_expected_positions", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_tm_expected_positions_account", table_name="ai_tm_expected_positions")
    op.drop_table("ai_tm_expected_positions")

    op.drop_index("ix_ai_tm_playbook_runs_playbook_ts", table_name="ai_tm_playbook_runs")
    op.drop_table("ai_tm_playbook_runs")

    op.drop_index("ix_ai_tm_playbooks_next_run", table_name="ai_tm_playbooks")
    op.drop_index("ix_ai_tm_playbooks_user_id", table_name="ai_tm_playbooks")
    op.drop_index("ix_ai_tm_playbooks_account_id", table_name="ai_tm_playbooks")
    op.drop_table("ai_tm_playbooks")

    op.drop_index("ix_ai_tm_trade_plans_user_ts", table_name="ai_tm_trade_plans")
    op.drop_index("ix_ai_tm_trade_plans_account_ts", table_name="ai_tm_trade_plans")
    op.drop_table("ai_tm_trade_plans")

