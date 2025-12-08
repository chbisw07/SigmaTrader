"""extend strategies with scope, owner, and expression templates

Revision ID: 0016
Revises: 0015
Create Date: 2025-12-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("owner_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column("scope", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column("dsl_expression", sa.Text(), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column("expression_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "is_builtin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("strategies", "is_builtin")
    op.drop_column("strategies", "expression_json")
    op.drop_column("strategies", "dsl_expression")
    op.drop_column("strategies", "scope")
    op.drop_column("strategies", "owner_id")
