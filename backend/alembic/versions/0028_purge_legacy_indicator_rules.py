"""Purge legacy indicator_rules definitions (Phase 1 cutover).

Revision ID: 0028
Revises: 0027
Create Date: 2025-12-17
"""

from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve historical Alert rows by detaching them from rules first.
    op.execute("UPDATE alerts SET rule_id = NULL WHERE rule_id IS NOT NULL")
    # Remove all legacy per-symbol/universe indicator rules.
    op.execute("DELETE FROM indicator_rules")


def downgrade() -> None:
    # Data purge is not reversible.
    pass
