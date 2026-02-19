"""Add AI chat message attachments.

Revision ID: 0076
Revises: 0075
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_tm_chat_messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "attachments_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_tm_chat_messages") as batch_op:
        batch_op.drop_column("attachments_json")

