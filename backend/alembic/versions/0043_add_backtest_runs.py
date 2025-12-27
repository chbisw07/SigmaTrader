"""Add backtest runs table.

Revision ID: 0043_add_backtest_runs
Revises: 0042
Create Date: 2025-12-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_add_backtest_runs"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "backtest_runs" in inspector.get_table_names():
        return

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="PENDING"
        ),
        sa.Column("title", sa.String(length=255)),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_backtest_runs_owner_id", "backtest_runs", ["owner_id"])
    op.create_index("ix_backtest_runs_created_at", "backtest_runs", ["created_at"])
    op.create_index("ix_backtest_runs_kind", "backtest_runs", ["kind"])
    op.create_index("ix_backtest_runs_status", "backtest_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_status", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_kind", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_created_at", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_owner_id", table_name="backtest_runs")
    op.drop_table("backtest_runs")
