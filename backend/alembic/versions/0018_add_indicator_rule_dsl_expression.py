"""add optional dsl_expression to indicator_rules

Revision ID: 0018
Revises: 0017
Create Date: 2025-12-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "indicator_rules",
        sa.Column("dsl_expression", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("indicator_rules", "dsl_expression")
