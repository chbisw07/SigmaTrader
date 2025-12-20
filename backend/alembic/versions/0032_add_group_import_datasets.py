"""Add group import datasets (dynamic columns for groups).

Revision ID: 0032
Revises: 0031
Create Date: 2025-12-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="TRADINGVIEW",
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("schema_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "symbol_mapping_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("group_id", name="ux_group_imports_group_id"),
    )
    op.create_index("ix_group_imports_group_id", "group_imports", ["group_id"])
    op.create_index("ix_group_imports_created_at", "group_imports", ["created_at"])

    op.create_table(
        "group_import_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "import_id",
            sa.Integer(),
            sa.ForeignKey("group_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column(
            "exchange",
            sa.String(length=32),
            nullable=False,
            server_default="NSE",
        ),
        sa.Column("values_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "import_id",
            "symbol",
            "exchange",
            name="ux_group_import_values_import_symbol_exchange",
        ),
    )
    op.create_index(
        "ix_group_import_values_import_id",
        "group_import_values",
        ["import_id"],
    )
    op.create_index(
        "ix_group_import_values_symbol_exchange",
        "group_import_values",
        ["symbol", "exchange"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_group_import_values_symbol_exchange",
        table_name="group_import_values",
    )
    op.drop_index("ix_group_import_values_import_id", table_name="group_import_values")
    op.drop_table("group_import_values")

    op.drop_index("ix_group_imports_created_at", table_name="group_imports")
    op.drop_index("ix_group_imports_group_id", table_name="group_imports")
    op.drop_table("group_imports")
