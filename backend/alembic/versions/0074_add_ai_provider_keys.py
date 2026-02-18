"""Add AI provider key store.

Revision ID: 0074
Revises: 0073
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("key_name", sa.String(length=64), nullable=False),
        sa.Column("key_ciphertext", sa.String(length=2048), nullable=False),
        sa.Column("key_masked", sa.String(length=64), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "key_name",
            name="ux_ai_provider_keys_user_provider_name",
        ),
    )
    op.create_index(
        "ix_ai_provider_keys_provider",
        "ai_provider_keys",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_provider_keys_provider", table_name="ai_provider_keys")
    op.drop_table("ai_provider_keys")

