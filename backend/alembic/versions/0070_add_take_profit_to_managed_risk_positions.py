"""Add take-profit distance to managed risk positions.

Revision ID: 0070
Revises: 0069
Create Date: 2026-02-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    try:
        return table in inspector.get_table_names()
    except Exception:
        return False


def _has_column(inspector, table: str, name: str) -> bool:
    try:
        cols = inspector.get_columns(table)
    except Exception:
        return False
    return any(c.get("name") == name for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "managed_risk_positions"):
        return

    if not _has_column(inspector, "managed_risk_positions", "take_profit_distance"):
        op.add_column(
            "managed_risk_positions",
            sa.Column("take_profit_distance", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "managed_risk_positions"):
        return

    if _has_column(inspector, "managed_risk_positions", "take_profit_distance"):
        op.drop_column("managed_risk_positions", "take_profit_distance")

