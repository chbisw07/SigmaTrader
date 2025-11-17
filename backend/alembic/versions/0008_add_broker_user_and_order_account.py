"""add broker_user_id and order broker_account_id

Revision ID: 0008
Revises: 0007
Create Date: 2025-11-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add broker_user_id to broker_connections and broker_account_id to orders."""

    bind = op.get_bind()
    inspector = inspect(bind)

    tables = inspector.get_table_names()

    if "broker_connections" in tables:
        broker_cols = {c["name"] for c in inspector.get_columns("broker_connections")}
        if "broker_user_id" not in broker_cols:
            op.add_column(
                "broker_connections",
                sa.Column("broker_user_id", sa.String(length=64), nullable=True),
            )

    if "orders" in tables:
        order_cols = {c["name"] for c in inspector.get_columns("orders")}
        if "broker_account_id" not in order_cols:
            op.add_column(
                "orders",
                sa.Column("broker_account_id", sa.String(length=64), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "orders" in tables:
        order_cols = {c["name"] for c in inspector.get_columns("orders")}
        if "broker_account_id" in order_cols:
            op.drop_column("orders", "broker_account_id")

    if "broker_connections" in tables:
        broker_cols = {c["name"] for c in inspector.get_columns("broker_connections")}
        if "broker_user_id" in broker_cols:
            op.drop_column("broker_connections", "broker_user_id")
