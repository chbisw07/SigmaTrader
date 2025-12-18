"""Add screener_runs table for v3 screener scans.

Revision ID: 0029
Revises: 0028
Create Date: 2025-12-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "screener_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="RUNNING"
        ),
        sa.Column("target_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("variables_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("condition_dsl", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "evaluation_cadence",
            sa.String(length=8),
            nullable=False,
            server_default="1m",
        ),
        sa.Column("total_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "evaluated_symbols", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("matched_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("results_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'DONE', 'ERROR')", name="ck_screener_runs_status"
        ),
    )
    op.create_index(
        "ix_screener_runs_user_created", "screener_runs", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_screener_runs_user_status", "screener_runs", ["user_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_screener_runs_user_status", table_name="screener_runs")
    op.drop_index("ix_screener_runs_user_created", table_name="screener_runs")
    op.drop_table("screener_runs")
