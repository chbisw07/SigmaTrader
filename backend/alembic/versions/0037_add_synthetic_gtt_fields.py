"""Add synthetic GTT (server-side conditional) fields to orders.

Revision ID: 0037
Revises: 0036
Create Date: 2025-12-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "synthetic_gtt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("orders", sa.Column("trigger_operator", sa.String(length=2)))
    op.add_column("orders", sa.Column("armed_at", sa.DateTime()))
    op.add_column("orders", sa.Column("last_checked_at", sa.DateTime()))
    op.add_column("orders", sa.Column("last_seen_price", sa.Float()))
    op.add_column("orders", sa.Column("triggered_at", sa.DateTime()))
    op.create_index(
        "ix_orders_synthetic_status",
        "orders",
        ["synthetic_gtt", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_orders_synthetic_status", table_name="orders")
    op.drop_column("orders", "triggered_at")
    op.drop_column("orders", "last_seen_price")
    op.drop_column("orders", "last_checked_at")
    op.drop_column("orders", "armed_at")
    op.drop_column("orders", "trigger_operator")
    op.drop_column("orders", "synthetic_gtt")
