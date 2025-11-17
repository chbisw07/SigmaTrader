"""add user_id to broker, alerts, orders

Revision ID: 0006
Revises: 0005
Create Date: 2025-11-17

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add user_id to broker/alert/order tables.

    This migration is written to be idempotent: if the columns already exist
    (e.g., because the schema was created via Base.metadata.create_all before
    running Alembic), it will simply return.
    """

    bind = op.get_bind()
    inspector = inspect(bind)

    # If alerts already has user_id, assume this migration has effectively
    # been applied and skip.
    alert_columns = {col["name"] for col in inspector.get_columns("alerts")}
    if "user_id" in alert_columns:
        return

    op.add_column(
        "broker_connections",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_broker_connections_user_id",
        "broker_connections",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "broker_secrets",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_broker_secrets_user_id",
        "broker_secrets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "alerts",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_alerts_user_id",
        "alerts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "orders",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_user_id",
        "orders",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_orders_user_id", "orders", type_="foreignkey")
    op.drop_column("orders", "user_id")

    op.drop_constraint("fk_alerts_user_id", "alerts", type_="foreignkey")
    op.drop_column("alerts", "user_id")

    op.drop_constraint(
        "fk_broker_secrets_user_id",
        "broker_secrets",
        type_="foreignkey",
    )
    op.drop_column("broker_secrets", "user_id")

    op.drop_constraint(
        "fk_broker_connections_user_id",
        "broker_connections",
        type_="foreignkey",
    )
    op.drop_column("broker_connections", "user_id")
