"""Add sent_at to orders.

Revision ID: 7bb039b9943c
Revises: 0068
Create Date: 2026-02-04 16:58:49.942802

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "7bb039b9943c"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("sent_at", sa.DateTime(timezone=True)))
    op.create_index("ix_orders_sent_at", "orders", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_sent_at", table_name="orders")
    op.drop_column("orders", "sent_at")
