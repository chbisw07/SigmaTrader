"""Add product-specific risk engine tables.

Revision ID: 0063
Revises: 0062
Create Date: 2026-01-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("product", sa.String(length=16), nullable=False, server_default="CNC"),
        sa.Column(
            "capital_per_trade",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_positions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_exposure_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "risk_per_trade_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "hard_risk_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "daily_loss_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "hard_daily_loss_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_consecutive_losses",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "drawdown_mode",
            sa.String(length=32),
            nullable=False,
            server_default="SETTINGS_BY_CATEGORY",
        ),
        sa.Column("force_exit_time", sa.String(length=8), nullable=True),
        sa.Column("entry_cutoff_time", sa.String(length=8), nullable=True),
        sa.Column("force_squareoff_time", sa.String(length=8), nullable=True),
        sa.Column("max_trades_per_day", sa.Integer(), nullable=True),
        sa.Column("max_trades_per_symbol_per_day", sa.Integer(), nullable=True),
        sa.Column("min_bars_between_trades", sa.Integer(), nullable=True),
        sa.Column("cooldown_after_loss_bars", sa.Integer(), nullable=True),
        sa.Column("slippage_guard_bps", sa.Float(), nullable=True),
        sa.Column("gap_guard_pct", sa.Float(), nullable=True),
        sa.Column("order_type_policy", sa.String(length=32), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ux_risk_profiles_name", "risk_profiles", ["name"], unique=True)
    op.create_index(
        "ix_risk_profiles_product_enabled",
        "risk_profiles",
        ["product", "enabled"],
        unique=False,
    )

    op.create_table(
        "symbol_risk_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "broker_name",
            sa.String(length=32),
            nullable=False,
            server_default="zerodha",
        ),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column(
            "exchange",
            sa.String(length=16),
            nullable=False,
            server_default="NSE",
        ),
        sa.Column(
            "risk_category",
            sa.String(length=16),
            nullable=False,
            server_default="LC",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ux_symbol_risk_categories_scope",
        "symbol_risk_categories",
        ["user_id", "broker_name", "symbol", "exchange"],
        unique=True,
    )
    op.create_index(
        "ix_symbol_risk_categories_user_symbol",
        "symbol_risk_categories",
        ["user_id", "broker_name", "symbol", "exchange"],
        unique=False,
    )

    op.create_table(
        "drawdown_thresholds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("product", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column(
            "caution_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "defense_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "hard_stop_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ux_drawdown_thresholds_scope",
        "drawdown_thresholds",
        ["user_id", "product", "category"],
        unique=True,
    )
    op.create_index(
        "ix_drawdown_thresholds_product_category",
        "drawdown_thresholds",
        ["product", "category"],
        unique=False,
    )

    op.create_table(
        "equity_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "equity",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "peak_equity",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "drawdown_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ux_equity_snapshots_scope",
        "equity_snapshots",
        ["user_id", "as_of_date"],
        unique=True,
    )
    op.create_index(
        "ix_equity_snapshots_user_date",
        "equity_snapshots",
        ["user_id", "as_of_date"],
        unique=False,
    )

    op.create_table(
        "alert_decision_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("alert_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="ALERT",
        ),
        sa.Column("strategy_ref", sa.String(length=255), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=True),
        sa.Column("exchange", sa.String(length=16), nullable=True),
        sa.Column("side", sa.String(length=8), nullable=True),
        sa.Column("trigger_price", sa.Float(), nullable=True),
        sa.Column("product_hint", sa.String(length=16), nullable=True),
        sa.Column("resolved_product", sa.String(length=16), nullable=True),
        sa.Column("risk_profile_id", sa.Integer(), nullable=True),
        sa.Column("risk_category", sa.String(length=16), nullable=True),
        sa.Column("drawdown_pct", sa.Float(), nullable=True),
        sa.Column("drawdown_state", sa.String(length=16), nullable=True),
        sa.Column(
            "decision",
            sa.String(length=16),
            nullable=False,
            server_default="BLOCKED",
        ),
        sa.Column(
            "reasons_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "details_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["risk_profile_id"], ["risk_profiles.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_alert_decision_logs_created",
        "alert_decision_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_alert_decision_logs_user_created",
        "alert_decision_logs",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_decision_logs_user_created", table_name="alert_decision_logs")
    op.drop_index("ix_alert_decision_logs_created", table_name="alert_decision_logs")
    op.drop_table("alert_decision_logs")

    op.drop_index("ix_equity_snapshots_user_date", table_name="equity_snapshots")
    op.drop_index("ux_equity_snapshots_scope", table_name="equity_snapshots")
    op.drop_table("equity_snapshots")

    op.drop_index(
        "ix_drawdown_thresholds_product_category",
        table_name="drawdown_thresholds",
    )
    op.drop_index("ux_drawdown_thresholds_scope", table_name="drawdown_thresholds")
    op.drop_table("drawdown_thresholds")

    op.drop_index(
        "ix_symbol_risk_categories_user_symbol",
        table_name="symbol_risk_categories",
    )
    op.drop_index("ux_symbol_risk_categories_scope", table_name="symbol_risk_categories")
    op.drop_table("symbol_risk_categories")

    op.drop_index("ix_risk_profiles_product_enabled", table_name="risk_profiles")
    op.drop_index("ux_risk_profiles_name", table_name="risk_profiles")
    op.drop_table("risk_profiles")

