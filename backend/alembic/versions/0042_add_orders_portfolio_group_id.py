"""Add portfolio_group_id to orders for portfolio attribution.

Revision ID: 0042
Revises: 0041
Create Date: 2025-12-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def has_column(table: str, column: str) -> bool:
        try:
            cols = inspector.get_columns(table)
        except Exception:
            return False
        return any(c.get("name") == column for c in cols)

    if not has_column("orders", "portfolio_group_id"):
        with op.batch_alter_table("orders") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "portfolio_group_id",
                    sa.Integer(),
                    nullable=True,
                )
            )
            batch_op.create_foreign_key(
                "fk_orders_portfolio_group_id",
                "groups",
                ["portfolio_group_id"],
                ["id"],
                ondelete="SET NULL",
            )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_orders_portfolio_group_id",
        "orders",
        ["portfolio_group_id"],
        if_not_exists=True,
    )


def downgrade() -> None:  # pragma: no cover
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "orders" not in inspector.get_table_names():
        return
    cols = [c.get("name") for c in inspector.get_columns("orders")]
    if "portfolio_group_id" in cols:
        op.drop_index("ix_orders_portfolio_group_id", table_name="orders")
        with op.batch_alter_table("orders") as batch_op:
            batch_op.drop_constraint(
                "fk_orders_portfolio_group_id", type_="foreignkey"
            )
            batch_op.drop_column("portfolio_group_id")
