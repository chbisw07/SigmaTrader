"""Add amount/qty input fields for basket allocation modes.

Revision ID: 0058
Revises: 0057
Create Date: 2026-01-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("group_members") as batch_op:
        batch_op.add_column(sa.Column("allocation_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("allocation_qty", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("group_members") as batch_op:
        batch_op.drop_column("allocation_qty")
        batch_op.drop_column("allocation_amount")

