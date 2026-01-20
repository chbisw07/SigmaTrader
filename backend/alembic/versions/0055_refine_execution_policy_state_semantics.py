"""Refine execution policy state semantics and safety fields.

Revision ID: 0055
Revises: 0054
Create Date: 2026-01-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_policy_state",
        sa.Column(
            "interval_source",
            sa.String(length=32),
            nullable=False,
            server_default="persisted",
        ),
    )
    op.add_column(
        "execution_policy_state",
        sa.Column(
            "default_interval_logged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "execution_policy_state",
        sa.Column("inflight_order_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "execution_policy_state",
        sa.Column("inflight_started_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "execution_policy_state",
        sa.Column("inflight_expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("execution_policy_state", "inflight_expires_at")
    op.drop_column("execution_policy_state", "inflight_started_at")
    op.drop_column("execution_policy_state", "inflight_order_id")
    op.drop_column("execution_policy_state", "default_interval_logged")
    op.drop_column("execution_policy_state", "interval_source")

