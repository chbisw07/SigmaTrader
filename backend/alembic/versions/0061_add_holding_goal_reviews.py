"""Add holding goal review history.

Revision ID: 0061
Revises: 0060
Create Date: 2026-01-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holding_goal_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("previous_review_date", sa.Date(), nullable=False),
        sa.Column("new_review_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["holding_goals.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_holding_goal_reviews_user",
        "holding_goal_reviews",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_holding_goal_reviews_goal",
        "holding_goal_reviews",
        ["goal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_holding_goal_reviews_goal", table_name="holding_goal_reviews")
    op.drop_index("ix_holding_goal_reviews_user", table_name="holding_goal_reviews")
    op.drop_table("holding_goal_reviews")
