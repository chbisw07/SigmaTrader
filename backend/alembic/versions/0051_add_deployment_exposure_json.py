"""Add deployment exposure summary field (v3).

Revision ID: 0051
Revises: 0050
Create Date: 2026-01-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, name: str) -> bool:
    try:
        cols = inspector.get_columns(table)
    except Exception:
        return False
    return any(c.get("name") == name for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "strategy_deployment_states" not in inspector.get_table_names():
        return

    if not _has_column(inspector, "strategy_deployment_states", "exposure_json"):
        op.add_column(
            "strategy_deployment_states",
            sa.Column("exposure_json", sa.Text()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "strategy_deployment_states" not in inspector.get_table_names():
        return
    if _has_column(inspector, "strategy_deployment_states", "exposure_json"):
        op.drop_column("strategy_deployment_states", "exposure_json")
