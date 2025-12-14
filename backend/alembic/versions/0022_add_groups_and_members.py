"""add groups and group members

Revision ID: 0022
Revises: 0021
Create Date: 2025-12-14

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="WATCHLIST",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('WATCHLIST', 'MODEL_PORTFOLIO', 'HOLDINGS_VIEW')",
            name="ck_groups_kind",
        ),
        sa.UniqueConstraint("owner_id", "name", name="ux_groups_owner_name"),
    )
    op.create_index("ix_groups_owner_id", "groups", ["owner_id"])
    op.create_index("ix_groups_kind", "groups", ["kind"])

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "group_id",
            "symbol",
            "exchange",
            name="ux_group_members_group_symbol_exchange",
        ),
    )
    op.create_index("ix_group_members_group_id", "group_members", ["group_id"])
    op.create_index(
        "ix_group_members_symbol_exchange",
        "group_members",
        ["symbol", "exchange"],
    )


def downgrade() -> None:
    op.drop_index("ix_group_members_symbol_exchange", table_name="group_members")
    op.drop_index("ix_group_members_group_id", table_name="group_members")
    op.drop_table("group_members")

    op.drop_index("ix_groups_kind", table_name="groups")
    op.drop_index("ix_groups_owner_id", table_name="groups")
    op.drop_table("groups")
