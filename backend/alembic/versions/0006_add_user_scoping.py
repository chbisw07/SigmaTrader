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

    with op.batch_alter_table("broker_connections") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_broker_connections_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("broker_secrets") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_broker_secrets_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_alerts_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_orders_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint("fk_orders_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_constraint("fk_alerts_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("broker_secrets") as batch_op:
        batch_op.drop_constraint("fk_broker_secrets_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("broker_connections") as batch_op:
        batch_op.drop_constraint(
            "fk_broker_connections_user_id",
            type_="foreignkey",
        )
        batch_op.drop_column("user_id")
