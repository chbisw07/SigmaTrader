"""Add covariance cache table for risk-based rebalance.

Revision ID: 0041
Revises: 0040
Create Date: 2025-12-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def has_table(name: str) -> bool:
        return name in inspector.get_table_names()

    if not has_table("risk_covariance_cache"):
        op.create_table(
            "risk_covariance_cache",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("universe_hash", sa.String(length=64), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("window_days", sa.Integer(), nullable=False),
            sa.Column("as_of_ts", sa.DateTime(), nullable=False),
            sa.Column("symbols_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("cov_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("vol_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("corr_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("observations", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "universe_hash",
                "timeframe",
                "window_days",
                "as_of_ts",
                name="ux_risk_cov_cache_key",
            ),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_risk_cov_cache_lookup",
        "risk_covariance_cache",
        ["universe_hash", "timeframe", "window_days", "as_of_ts"],
        if_not_exists=True,
    )


def downgrade() -> None:  # pragma: no cover
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "risk_covariance_cache" in inspector.get_table_names():
        op.drop_index("ix_risk_cov_cache_lookup", table_name="risk_covariance_cache")
        op.drop_table("risk_covariance_cache")
