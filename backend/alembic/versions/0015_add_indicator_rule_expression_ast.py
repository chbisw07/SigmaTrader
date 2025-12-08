"""add expression_json and target metadata to indicator_rules

Revision ID: 0015
Revises: 0014
Create Date: 2025-12-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "indicator_rules",
        sa.Column("expression_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "indicator_rules",
        sa.Column("target_type", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "indicator_rules",
        sa.Column("target_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "indicator_rules",
        sa.Column("last_evaluated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("indicator_rules", "last_evaluated_at")
    op.drop_column("indicator_rules", "target_id")
    op.drop_column("indicator_rules", "target_type")
    op.drop_column("indicator_rules", "expression_json")
