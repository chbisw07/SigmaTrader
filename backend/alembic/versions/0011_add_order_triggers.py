"""Add trigger fields to orders table.

Revision ID: 0011_add_order_triggers
Revises: 0010_add_user_theme
Create Date: 2025-11-18 00:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

RevisionType = Union[str, None]

# revision identifiers, used by Alembic.
revision: RevisionType = "0011"
down_revision: RevisionType = "0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("trigger_price", sa.Float(), nullable=True))
    op.add_column("orders", sa.Column("trigger_percent", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "trigger_percent")
    op.drop_column("orders", "trigger_price")
