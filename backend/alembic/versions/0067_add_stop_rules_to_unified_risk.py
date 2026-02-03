"""Add stop-distance settings to unified risk tables.

Revision ID: 0067
Revises: 0066
Create Date: 2026-02-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # risk_profiles: stop-distance configuration (used for per-trade risk caps).
    op.add_column(
        "risk_profiles",
        sa.Column(
            "stop_loss_mandatory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "stop_reference",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'ATR'"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column("atr_period", sa.Integer(), nullable=False, server_default=sa.text("14")),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "atr_mult_initial_stop",
            sa.Float(),
            nullable=False,
            server_default=sa.text("2.0"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "fallback_stop_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "min_stop_distance_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "max_stop_distance_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("3.0"),
        ),
    )

    # risk_source_overrides: optional per-source overrides of profile stop settings + per-trade risk caps.
    op.add_column("risk_source_overrides", sa.Column("risk_per_trade_pct", sa.Float(), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("hard_risk_pct", sa.Float(), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("stop_loss_mandatory", sa.Boolean(), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("stop_reference", sa.String(length=16), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("atr_period", sa.Integer(), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("atr_mult_initial_stop", sa.Float(), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("fallback_stop_pct", sa.Float(), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("min_stop_distance_pct", sa.Float(), nullable=True))
    op.add_column("risk_source_overrides", sa.Column("max_stop_distance_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("risk_source_overrides", "max_stop_distance_pct")
    op.drop_column("risk_source_overrides", "min_stop_distance_pct")
    op.drop_column("risk_source_overrides", "fallback_stop_pct")
    op.drop_column("risk_source_overrides", "atr_mult_initial_stop")
    op.drop_column("risk_source_overrides", "atr_period")
    op.drop_column("risk_source_overrides", "stop_reference")
    op.drop_column("risk_source_overrides", "stop_loss_mandatory")
    op.drop_column("risk_source_overrides", "hard_risk_pct")
    op.drop_column("risk_source_overrides", "risk_per_trade_pct")

    op.drop_column("risk_profiles", "max_stop_distance_pct")
    op.drop_column("risk_profiles", "min_stop_distance_pct")
    op.drop_column("risk_profiles", "fallback_stop_pct")
    op.drop_column("risk_profiles", "atr_mult_initial_stop")
    op.drop_column("risk_profiles", "atr_period")
    op.drop_column("risk_profiles", "stop_reference")
    op.drop_column("risk_profiles", "stop_loss_mandatory")
