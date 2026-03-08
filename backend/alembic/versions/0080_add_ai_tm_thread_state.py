"""Add AI thread state.

Revision ID: 0080
Revises: 0079
Create Date: 2026-03-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_tm_thread_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "thread_id", name="ux_ai_tm_thread_state_account_thread"),
    )
    op.create_index(
        "ix_ai_tm_thread_state_account_ts",
        "ai_tm_thread_state",
        ["account_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_tm_thread_state_user_ts",
        "ai_tm_thread_state",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tm_thread_state_user_ts", table_name="ai_tm_thread_state")
    op.drop_index("ix_ai_tm_thread_state_account_ts", table_name="ai_tm_thread_state")
    op.drop_table("ai_tm_thread_state")

