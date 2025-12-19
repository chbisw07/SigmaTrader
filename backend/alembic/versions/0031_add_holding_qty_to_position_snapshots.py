"""Add holding_qty to position_snapshots.

Revision ID: 0031
Revises: 0030
Create Date: 2025-12-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("position_snapshots") as batch_op:
        batch_op.add_column(sa.Column("holding_qty", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("position_snapshots") as batch_op:
        batch_op.drop_column("holding_qty")
