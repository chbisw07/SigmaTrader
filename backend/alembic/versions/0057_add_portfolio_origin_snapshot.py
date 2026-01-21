"""Add portfolio origin + snapshot linkage fields.

Revision ID: 0057
Revises: 0056
Create Date: 2026-01-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.add_column(sa.Column("origin_basket_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("bought_at", sa.DateTime(), nullable=True))

    op.create_index("ix_groups_origin_basket_id", "groups", ["origin_basket_id"])


def downgrade() -> None:
    op.drop_index("ix_groups_origin_basket_id", table_name="groups")

    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_column("bought_at")
        batch_op.drop_column("origin_basket_id")

