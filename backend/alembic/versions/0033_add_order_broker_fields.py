"""Add broker-agnostic order fields (broker_name, broker_order_id).

Revision ID: 0033
Revises: 0032
Create Date: 2025-12-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "broker_name",
            sa.String(length=32),
            nullable=False,
            server_default="zerodha",
        ),
    )
    op.add_column(
        "orders",
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
    )

    # Backfill broker_order_id for existing Zerodha orders.
    op.execute(
        "UPDATE orders SET broker_order_id = zerodha_order_id "
        "WHERE broker_order_id IS NULL AND zerodha_order_id IS NOT NULL"
    )

    # Replace the Zerodha-specific lookup index with a broker-aware one.
    op.drop_index("ix_orders_zerodha_order_id", table_name="orders")
    op.create_index(
        "ix_orders_broker_name_order_id",
        "orders",
        ["broker_name", "broker_order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_orders_broker_name_order_id", table_name="orders")
    op.create_index(
        "ix_orders_zerodha_order_id",
        "orders",
        ["zerodha_order_id"],
    )
    op.drop_column("orders", "broker_order_id")
    op.drop_column("orders", "broker_name")
