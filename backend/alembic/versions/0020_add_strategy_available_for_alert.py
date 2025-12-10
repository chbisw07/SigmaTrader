"""add available_for_alert flag on strategies

Revision ID: 0020
Revises: 0019
Create Date: 2025-12-10

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column(
            "available_for_alert",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("strategies", "available_for_alert")
