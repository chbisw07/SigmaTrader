"""Add holding goals for intent tracking.

Revision ID: 0059
Revises: 0058
Create Date: 2026-01-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holding_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=24), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.Column("target_type", sa.String(length=24), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
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
            "broker_name",
            "symbol",
            "exchange",
            name="ux_holding_goals_scope",
        ),
    )
    op.create_index(
        "ix_holding_goals_user_broker",
        "holding_goals",
        ["user_id", "broker_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_holding_goals_user_broker", table_name="holding_goals")
    op.drop_table("holding_goals")
