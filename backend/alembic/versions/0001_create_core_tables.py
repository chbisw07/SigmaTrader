"""create core tables

Revision ID: 0001
Revises: None
Create Date: 2025-11-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "execution_mode",
            sa.String(length=16),
            nullable=False,
            server_default="MANUAL",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "execution_mode IN ('AUTO', 'MANUAL')",
            name="ck_strategies_execution_mode",
        ),
    )
    op.create_index(
        "ix_strategies_execution_mode",
        "strategies",
        ["execution_mode"],
    )

    op.create_table(
        "risk_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scope",
            sa.String(length=16),
            nullable=False,
            server_default="STRATEGY",
        ),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("max_order_value", sa.Float(), nullable=True),
        sa.Column("max_quantity_per_order", sa.Float(), nullable=True),
        sa.Column("max_daily_loss", sa.Float(), nullable=True),
        sa.Column(
            "allow_short_selling",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("max_open_positions", sa.Integer(), nullable=True),
        sa.Column(
            "clamp_mode",
            sa.String(length=16),
            nullable=False,
            server_default="CLAMP",
        ),
        sa.Column("symbol_whitelist", sa.Text(), nullable=True),
        sa.Column("symbol_blacklist", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_risk_settings_strategy_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "scope",
            "strategy_id",
            name="ux_risk_settings_scope_strategy",
        ),
        sa.CheckConstraint(
            "scope IN ('GLOBAL', 'STRATEGY')", name="ck_risk_settings_scope"
        ),
        sa.CheckConstraint(
            "(scope = 'GLOBAL' AND strategy_id IS NULL) OR "
            "(scope = 'STRATEGY' AND strategy_id IS NOT NULL)",
            name="ck_risk_settings_scope_strategy",
        ),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("interval", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column(
            "platform",
            sa.String(length=32),
            nullable=False,
            server_default="TRADINGVIEW",
        ),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("bar_time", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_alerts_strategy_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_alerts_strategy_time",
        "alerts",
        ["strategy_id", "received_at"],
    )
    op.create_index(
        "ix_alerts_symbol_time",
        "alerts",
        ["symbol", "received_at"],
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), nullable=True),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column(
            "order_type",
            sa.String(length=16),
            nullable=False,
            server_default="MARKET",
        ),
        sa.Column(
            "product",
            sa.String(length=16),
            nullable=False,
            server_default="MIS",
        ),
        sa.Column(
            "gtt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="WAITING",
        ),
        sa.Column(
            "mode",
            sa.String(length=16),
            nullable=False,
            server_default="MANUAL",
        ),
        sa.Column("zerodha_order_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "simulated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            name="fk_orders_alert_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_orders_strategy_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_orders_strategy_status",
        "orders",
        ["strategy_id", "status"],
    )
    op.create_index(
        "ix_orders_symbol_time",
        "orders",
        ["symbol", "created_at"],
    )
    op.create_index(
        "ix_orders_zerodha_order_id",
        "orders",
        ["zerodha_order_id"],
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("product", sa.String(length=16), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column(
            "pnl",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "symbol",
            "product",
            name="ux_positions_symbol_product",
        ),
    )

    op.create_table(
        "analytics_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_order_id", sa.Integer(), nullable=False),
        sa.Column("exit_order_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.Column("r_multiple", sa.Float(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_order_id"],
            ["orders.id"],
            name="fk_analytics_trades_entry_order_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["exit_order_id"],
            ["orders.id"],
            name="fk_analytics_trades_exit_order_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_analytics_trades_strategy_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_analytics_trades_strategy_closed_at",
        "analytics_trades",
        ["strategy_id", "closed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analytics_trades_strategy_closed_at",
        table_name="analytics_trades",
    )
    op.drop_table("analytics_trades")
    op.drop_table("positions")
    op.drop_index("ix_orders_zerodha_order_id", table_name="orders")
    op.drop_index("ix_orders_symbol_time", table_name="orders")
    op.drop_index("ix_orders_strategy_status", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_alerts_symbol_time", table_name="alerts")
    op.drop_index("ix_alerts_strategy_time", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("risk_settings")
    op.drop_index("ix_strategies_execution_mode", table_name="strategies")
    op.drop_table("strategies")
