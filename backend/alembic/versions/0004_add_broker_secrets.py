"""add broker_secrets table

Revision ID: 0004
Revises: 0003
Create Date: 2025-11-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_secrets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value_encrypted", sa.String(length=1024), nullable=False),
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
            "key",
            name="ux_broker_secrets_broker_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("broker_secrets")
