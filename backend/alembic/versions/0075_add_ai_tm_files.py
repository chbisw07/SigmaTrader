"""Add AI Trading Manager file store.

Revision ID: 0075
Revises: 0074
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_tm_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("file_id", name="ux_ai_tm_files_file_id"),
    )
    op.create_index(
        "ix_ai_tm_files_user_ts",
        "ai_tm_files",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tm_files_user_ts", table_name="ai_tm_files")
    op.drop_table("ai_tm_files")

