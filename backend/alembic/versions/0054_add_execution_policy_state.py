"""Add execution policy state table for trade frequency and loss controls.

Revision ID: 0054
Revises: 0053
Create Date: 2026-01-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_policy_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strategy_ref", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column(
            "product",
            sa.String(length=16),
            nullable=False,
            server_default="MIS",
        ),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("trades_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_trade_time", sa.DateTime(), nullable=True),
        sa.Column("last_trade_bar_index", sa.Integer(), nullable=True),
        sa.Column(
            "consecutive_losses",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_loss_time", sa.DateTime(), nullable=True),
        sa.Column("last_loss_bar_index", sa.Integer(), nullable=True),
        sa.Column("paused_until", sa.DateTime(), nullable=True),
        sa.Column("paused_reason", sa.String(length=255), nullable=True),
        sa.Column("open_side", sa.String(length=8), nullable=True),
        sa.Column("open_qty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("open_avg_price", sa.Float(), nullable=True),
        sa.Column("open_realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "strategy_ref",
            "symbol",
            "product",
            name="ux_execution_policy_state_scope",
        ),
    )
    op.create_index(
        "ix_execution_policy_state_user_strategy",
        "execution_policy_state",
        ["user_id", "strategy_ref"],
        unique=False,
    )
    op.create_index(
        "ix_execution_policy_state_updated_at",
        "execution_policy_state",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_execution_policy_state_updated_at",
        table_name="execution_policy_state",
    )
    op.drop_index(
        "ix_execution_policy_state_user_strategy",
        table_name="execution_policy_state",
    )
    op.drop_table("execution_policy_state")
