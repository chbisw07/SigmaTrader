"""Add AI operator payloads.

Revision ID: 0077
Revises: 0076
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_tm_operator_payloads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payload_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_call_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("payload_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("payload_id", name="ux_ai_tm_operator_payloads_payload_id"),
    )
    op.create_index(
        "ix_ai_tm_operator_payloads_decision_ts",
        "ai_tm_operator_payloads",
        ["decision_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_tm_operator_payloads_user_ts",
        "ai_tm_operator_payloads",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tm_operator_payloads_user_ts", table_name="ai_tm_operator_payloads")
    op.drop_index("ix_ai_tm_operator_payloads_decision_ts", table_name="ai_tm_operator_payloads")
    op.drop_table("ai_tm_operator_payloads")
