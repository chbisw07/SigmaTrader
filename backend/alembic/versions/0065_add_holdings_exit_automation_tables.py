"""Add Holdings Exit Automation tables (subscriptions + audit events).

Revision ID: 0065
Revises: 0064
Create Date: 2026-02-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holding_exit_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
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
            "product",
            sa.String(length=16),
            nullable=False,
            server_default="CNC",
        ),
        sa.Column("trigger_kind", sa.String(length=32), nullable=False),
        sa.Column("trigger_value", sa.Float(), nullable=False),
        sa.Column(
            "price_source",
            sa.String(length=16),
            nullable=False,
            server_default="LTP",
        ),
        sa.Column("size_mode", sa.String(length=32), nullable=False),
        sa.Column("size_value", sa.Float(), nullable=False),
        sa.Column("min_qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "order_type",
            sa.String(length=16),
            nullable=False,
            server_default="MARKET",
        ),
        sa.Column(
            "dispatch_mode",
            sa.String(length=16),
            nullable=False,
            server_default="MANUAL",
        ),
        sa.Column(
            "execution_target",
            sa.String(length=16),
            nullable=False,
            server_default="LIVE",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "pending_order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("next_eval_at", sa.DateTime(), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.Column("trigger_key", sa.String(length=255), nullable=True),
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
        sa.CheckConstraint(
            (
                "trigger_kind IN ('TARGET_ABS_PRICE','TARGET_PCT_FROM_AVG_BUY',"
                "'DRAWDOWN_ABS_PRICE','DRAWDOWN_PCT_FROM_PEAK')"
            ),
            name="ck_holding_exit_subscriptions_trigger_kind",
        ),
        sa.CheckConstraint(
            "price_source IN ('LTP')",
            name="ck_holding_exit_subscriptions_price_source",
        ),
        sa.CheckConstraint(
            "size_mode IN ('ABS_QTY','PCT_OF_POSITION')",
            name="ck_holding_exit_subscriptions_size_mode",
        ),
        sa.CheckConstraint(
            "order_type IN ('MARKET')",
            name="ck_holding_exit_subscriptions_order_type",
        ),
        sa.CheckConstraint(
            "dispatch_mode IN ('MANUAL','AUTO')",
            name="ck_holding_exit_subscriptions_dispatch_mode",
        ),
        sa.CheckConstraint(
            "execution_target IN ('LIVE','PAPER')",
            name="ck_holding_exit_subscriptions_execution_target",
        ),
        sa.CheckConstraint(
            "product IN ('CNC','MIS')",
            name="ck_holding_exit_subscriptions_product",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','PAUSED','TRIGGERED_PENDING','ORDER_CREATED','COMPLETED','ERROR')",
            name="ck_holding_exit_subscriptions_status",
        ),
        sa.UniqueConstraint(
            "user_id",
            "broker_name",
            "exchange",
            "symbol",
            "product",
            "trigger_kind",
            "trigger_value",
            "size_mode",
            "size_value",
            name="ux_holding_exit_subscriptions_dedup",
        ),
    )

    op.create_index(
        "ix_holding_exit_subscriptions_status_broker_user",
        "holding_exit_subscriptions",
        ["status", "broker_name", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_holding_exit_subscriptions_symbol_scope",
        "holding_exit_subscriptions",
        ["broker_name", "exchange", "symbol", "product"],
        unique=False,
    )
    op.create_index(
        "ix_holding_exit_subscriptions_next_eval_at",
        "holding_exit_subscriptions",
        ["next_eval_at"],
        unique=False,
    )

    op.create_table(
        "holding_exit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("holding_exit_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "event_ts",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("price_snapshot_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            (
                "event_type IN ('SUB_CREATED','SUB_UPDATED','SUB_PAUSED','SUB_RESUMED',"
                "'EVAL','EVAL_SKIPPED_MISSING_QUOTE','EVAL_SKIPPED_BROKER_UNAVAILABLE',"
                "'TRIGGER_MET','ORDER_CREATED','ORDER_DISPATCHED','ORDER_FAILED',"
                "'EXIT_QUEUED_DUE_TO_PENDING_EXIT','SUB_COMPLETED','SUB_ERROR')"
            ),
            name="ck_holding_exit_events_event_type",
        ),
    )

    op.create_index(
        "ix_holding_exit_events_sub_ts",
        "holding_exit_events",
        ["subscription_id", "event_ts"],
        unique=False,
    )
    op.create_index(
        "ix_holding_exit_events_type_ts",
        "holding_exit_events",
        ["event_type", "event_ts"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_holding_exit_events_type_ts", table_name="holding_exit_events")
    op.drop_index("ix_holding_exit_events_sub_ts", table_name="holding_exit_events")
    op.drop_table("holding_exit_events")

    op.drop_index(
        "ix_holding_exit_subscriptions_next_eval_at",
        table_name="holding_exit_subscriptions",
    )
    op.drop_index(
        "ix_holding_exit_subscriptions_symbol_scope",
        table_name="holding_exit_subscriptions",
    )
    op.drop_index(
        "ix_holding_exit_subscriptions_status_broker_user",
        table_name="holding_exit_subscriptions",
    )
    op.drop_table("holding_exit_subscriptions")
