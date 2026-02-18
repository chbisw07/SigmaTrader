"""Add authorization metadata to AI TM playbooks/runs.

Revision ID: 0073
Revises: 0072
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_tm_playbooks",
        sa.Column("armed_by_message_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ai_tm_playbook_runs",
        sa.Column("authorization_message_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_tm_playbook_runs", "authorization_message_id")
    op.drop_column("ai_tm_playbooks", "armed_by_message_id")

