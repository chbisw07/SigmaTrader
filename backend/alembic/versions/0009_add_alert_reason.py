"""add reason column to alerts

Revision ID: 0009
Revises: 0008
Create Date: 2025-11-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "alerts" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("alerts")}
    if "reason" not in columns:
        op.add_column("alerts", sa.Column("reason", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "alerts" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("alerts")}
    if "reason" in columns:
        op.drop_column("alerts", "reason")
