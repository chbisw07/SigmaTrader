"""Add unified risk settings tables.

Revision ID: 0066
Revises: 0065
Create Date: 2026-02-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_global_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("singleton_key", sa.String(length=16), nullable=False, server_default="GLOBAL"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("manual_override_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("baseline_equity_inr", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ux_risk_global_config_singleton", "risk_global_config", ["singleton_key"], unique=True)

    op.create_table(
        "risk_source_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_bucket", sa.String(length=16), nullable=False),
        sa.Column("product", sa.String(length=16), nullable=False, server_default="CNC"),
        sa.Column("allow_product", sa.Boolean(), nullable=True),
        sa.Column("allow_short_selling", sa.Boolean(), nullable=True),
        sa.Column("max_order_value_pct", sa.Float(), nullable=True),
        sa.Column("max_order_value_abs", sa.Float(), nullable=True),
        sa.Column("max_quantity_per_order", sa.Float(), nullable=True),
        sa.Column("capital_per_trade", sa.Float(), nullable=True),
        sa.Column("max_positions", sa.Integer(), nullable=True),
        sa.Column("max_exposure_pct", sa.Float(), nullable=True),
        sa.Column("daily_loss_pct", sa.Float(), nullable=True),
        sa.Column("hard_daily_loss_pct", sa.Float(), nullable=True),
        sa.Column("max_consecutive_losses", sa.Integer(), nullable=True),
        sa.Column("entry_cutoff_time", sa.String(length=8), nullable=True),
        sa.Column("force_squareoff_time", sa.String(length=8), nullable=True),
        sa.Column("max_trades_per_day", sa.Integer(), nullable=True),
        sa.Column("max_trades_per_symbol_per_day", sa.Integer(), nullable=True),
        sa.Column("min_bars_between_trades", sa.Integer(), nullable=True),
        sa.Column("cooldown_after_loss_bars", sa.Integer(), nullable=True),
        sa.Column("slippage_guard_bps", sa.Float(), nullable=True),
        sa.Column("gap_guard_pct", sa.Float(), nullable=True),
        sa.Column("order_type_policy", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "source_bucket IN ('TRADINGVIEW', 'SIGMATRADER')",
            name="ck_risk_source_overrides_source_bucket",
        ),
        sa.CheckConstraint(
            "product IN ('CNC', 'MIS')",
            name="ck_risk_source_overrides_product",
        ),
        sa.UniqueConstraint("source_bucket", "product", name="ux_risk_source_overrides_scope"),
    )
    op.create_index(
        "ix_risk_source_overrides_source_product",
        "risk_source_overrides",
        ["source_bucket", "product"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_risk_source_overrides_source_product", table_name="risk_source_overrides")
    op.drop_table("risk_source_overrides")
    op.drop_index("ux_risk_global_config_singleton", table_name="risk_global_config")
    op.drop_table("risk_global_config")

