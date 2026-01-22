"""Add basket config + freeze fields for MODEL_PORTFOLIO groups.

Revision ID: 0056
Revises: 0055
Create Date: 2026-01-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.add_column(sa.Column("funds", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("allocation_mode", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(sa.Column("frozen_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("group_members") as batch_op:
        batch_op.add_column(sa.Column("frozen_price", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "weight_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("group_members") as batch_op:
        batch_op.drop_column("weight_locked")
        batch_op.drop_column("frozen_price")

    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_column("frozen_at")
        batch_op.drop_column("allocation_mode")
        batch_op.drop_column("funds")
