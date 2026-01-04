"""Add deployment order attribution + idempotency fields.

Revision ID: 0047
Revises: 0046_add_strategy_deployment_job_queue
Create Date: 2026-01-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046_add_strategy_deployment_job_queue"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, name: str) -> bool:
    try:
        cols = inspector.get_columns(table)
    except Exception:
        return False
    return any(c.get("name") == name for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "orders" not in inspector.get_table_names():
        return

    if not _has_column(inspector, "orders", "deployment_id"):
        op.add_column(
            "orders",
            sa.Column(
                "deployment_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployments.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _has_column(inspector, "orders", "deployment_action_id"):
        op.add_column(
            "orders",
            sa.Column(
                "deployment_action_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployment_actions.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _has_column(inspector, "orders", "client_order_id"):
        op.add_column(
            "orders",
            sa.Column("client_order_id", sa.String(length=128)),
        )

    inspector = sa.inspect(bind)
    existing = {i.get("name") for i in inspector.get_indexes("orders")}
    for name, cols, unique in [
        ("ix_orders_deployment_id", ["deployment_id"], False),
        ("ux_orders_client_order_id", ["client_order_id"], True),
        ("ix_orders_deployment_action_id", ["deployment_action_id"], False),
    ]:
        if name not in existing:
            op.create_index(name, "orders", cols, unique=unique)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "orders" not in inspector.get_table_names():
        return

    existing = {i.get("name") for i in inspector.get_indexes("orders")}
    for name in [
        "ix_orders_deployment_action_id",
        "ux_orders_client_order_id",
        "ix_orders_deployment_id",
    ]:
        if name in existing:
            op.drop_index(name, table_name="orders")

    # SQLite doesn't support dropping columns cleanly; keep as no-op for downgrade.
