"""add broker_connections table

Revision ID: 0002
Revises: 0001
Create Date: 2025-11-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("access_token_encrypted", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "broker_name",
            name="ux_broker_connections_broker_name",
        ),
    )


def downgrade() -> None:
    op.drop_table("broker_connections")
