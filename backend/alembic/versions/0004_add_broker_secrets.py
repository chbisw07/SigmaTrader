"""add broker_secrets table

Revision ID: 0004
Revises: 0003
Create Date: 2025-11-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "broker_secrets" in inspector.get_table_names():
        # Table already exists (e.g., created via Base.metadata.create_all
        # before this migration was introduced). Make the migration
        # idempotent so alembic upgrade can continue.
        return

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
