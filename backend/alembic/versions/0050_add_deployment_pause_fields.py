"""Add deployment pause/resume fields (v3).

Revision ID: 0050
Revises: 0049
Create Date: 2026-01-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
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

    for name, col in [
        ("paused_at", sa.Column("paused_at", sa.DateTime(timezone=True))),
        ("resumed_at", sa.Column("resumed_at", sa.DateTime(timezone=True))),
        ("pause_reason", sa.Column("pause_reason", sa.String(length=255))),
    ]:
        if not _has_column(inspector, "strategy_deployment_states", name):
            op.add_column("strategy_deployment_states", col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "strategy_deployment_states" not in inspector.get_table_names():
        return
    for col in ["pause_reason", "resumed_at", "paused_at"]:
        if _has_column(inspector, "strategy_deployment_states", col):
            op.drop_column("strategy_deployment_states", col)
