"""Add holdings summary snapshots.

Revision ID: 0069
Revises: 7bb039b9943c
Create Date: 2026-02-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "7bb039b9943c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holdings_summary_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "broker_name",
            sa.String(length=32),
            nullable=False,
            server_default="zerodha",
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "holdings_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("funds_available", sa.Float(), nullable=True),
        sa.Column("invested", sa.Float(), nullable=True),
        sa.Column("equity_value", sa.Float(), nullable=True),
        sa.Column("account_value", sa.Float(), nullable=True),
        sa.Column("total_pnl_pct", sa.Float(), nullable=True),
        sa.Column("today_pnl_pct", sa.Float(), nullable=True),
        sa.Column("overall_win_rate", sa.Float(), nullable=True),
        sa.Column("today_win_rate", sa.Float(), nullable=True),
        sa.Column("alpha_annual_pct", sa.Float(), nullable=True),
        sa.Column("beta", sa.Float(), nullable=True),
        sa.Column("cagr_1y_pct", sa.Float(), nullable=True),
        sa.Column("cagr_2y_pct", sa.Float(), nullable=True),
        sa.Column("cagr_1y_coverage_pct", sa.Float(), nullable=True),
        sa.Column("cagr_2y_coverage_pct", sa.Float(), nullable=True),
        sa.Column("benchmark_symbol", sa.String(length=128), nullable=True),
        sa.Column("benchmark_exchange", sa.String(length=16), nullable=True),
        sa.Column("risk_free_rate_pct", sa.Float(), nullable=True),
        sa.UniqueConstraint(
            "user_id",
            "broker_name",
            "as_of_date",
            name="ux_holdings_summary_snapshots_user_broker_date",
        ),
    )
    op.create_index(
        "ix_holdings_summary_snapshots_broker_date",
        "holdings_summary_snapshots",
        ["broker_name", "as_of_date"],
    )
    op.create_index(
        "ix_holdings_summary_snapshots_user_date",
        "holdings_summary_snapshots",
        ["user_id", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_holdings_summary_snapshots_user_date",
        table_name="holdings_summary_snapshots",
    )
    op.drop_index(
        "ix_holdings_summary_snapshots_broker_date",
        table_name="holdings_summary_snapshots",
    )
    op.drop_table("holdings_summary_snapshots")

