"""Add orders.execution_target.

Revision ID: 0024
Revises: 0023
Create Date: 2025-12-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "execution_target",
                sa.String(length=16),
                nullable=False,
                server_default="LIVE",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("execution_target")
