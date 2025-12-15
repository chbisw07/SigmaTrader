"""Add group member reference qty/price and PORTFOLIO kind.

Revision ID: 0023
Revises: 0022
Create Date: 2025-12-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_constraint("ck_groups_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_groups_kind",
            "kind IN ('WATCHLIST', 'MODEL_PORTFOLIO', 'HOLDINGS_VIEW', 'PORTFOLIO')",
        )

    with op.batch_alter_table("group_members") as batch_op:
        batch_op.add_column(sa.Column("reference_qty", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reference_price", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("group_members") as batch_op:
        batch_op.drop_column("reference_price")
        batch_op.drop_column("reference_qty")

    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_constraint("ck_groups_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_groups_kind",
            "kind IN ('WATCHLIST', 'MODEL_PORTFOLIO', 'HOLDINGS_VIEW')",
        )
