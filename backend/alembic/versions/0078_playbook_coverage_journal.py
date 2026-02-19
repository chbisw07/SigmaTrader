"""Playbook + coverage + journal tables.

Revision ID: 0078
Revises: 0077
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_tm_position_shadows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shadow_id", sa.String(length=64), nullable=False),
        sa.Column("broker_account_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("product", sa.String(length=16), nullable=False, server_default="CNC"),
        sa.Column("side", sa.String(length=8), nullable=False, server_default="LONG"),
        sa.Column("qty_current", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_price", sa.Float(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("status", sa.String(length=8), nullable=False, server_default="OPEN"),
        sa.Column("st_trade_id", sa.String(length=64), nullable=True),
        sa.Column("broker_position_key_hash", sa.String(length=64), nullable=True),
        sa.Column("broker_instrument_id_hash", sa.String(length=64), nullable=True),
        sa.Column("ltp", sa.Float(), nullable=True),
        sa.Column("pnl_abs", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("shadow_id", name="ux_ai_tm_position_shadows_shadow_id"),
    )
    op.create_index(
        "ix_ai_tm_position_shadows_account_status",
        "ai_tm_position_shadows",
        ["broker_account_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_tm_position_shadows_symbol_product",
        "ai_tm_position_shadows",
        ["symbol", "product"],
        unique=False,
    )
    op.create_index(
        "ix_ai_tm_position_shadows_last_seen",
        "ai_tm_position_shadows",
        ["last_seen_at"],
        unique=False,
    )

    op.create_table(
        "ai_tm_manage_playbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("playbook_id", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=24), nullable=False, server_default="POSITION"),
        sa.Column("scope_key", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="OBSERVE"),
        sa.Column("horizon", sa.String(length=16), nullable=False, server_default="SWING"),
        sa.Column("review_cadence_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("exit_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("scale_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("execution_style", sa.String(length=24), nullable=False, server_default="LIMIT_BBO"),
        sa.Column("allow_strategy_exits", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("behavior_on_strategy_exit", sa.String(length=32), nullable=False, server_default="ALLOW_AS_IS"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("playbook_id", name="ux_ai_tm_manage_playbooks_playbook_id"),
    )
    op.create_index(
        "ix_ai_tm_manage_playbooks_scope",
        "ai_tm_manage_playbooks",
        ["scope_type", "scope_key"],
        unique=False,
    )
    op.create_index(
        "ix_ai_tm_manage_playbooks_enabled",
        "ai_tm_manage_playbooks",
        ["enabled"],
        unique=False,
    )

    op.create_table(
        "ai_tm_journal_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("forecast_id", sa.String(length=64), nullable=False),
        sa.Column("position_shadow_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("author", sa.String(length=8), nullable=False, server_default="USER"),
        sa.Column("outlook_pct", sa.Float(), nullable=True),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("rationale_tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("thesis_text", sa.Text(), nullable=True),
        sa.Column("invalidation_text", sa.Text(), nullable=True),
        sa.UniqueConstraint("forecast_id", name="ux_ai_tm_journal_forecasts_forecast_id"),
    )
    op.create_index(
        "ix_ai_tm_journal_forecasts_shadow_ts",
        "ai_tm_journal_forecasts",
        ["position_shadow_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ai_tm_journal_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("position_shadow_id", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="SYSTEM"),
        sa.Column("intent_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("riskgate_result_json", sa.Text(), nullable=True),
        sa.Column("playbook_result_json", sa.Text(), nullable=True),
        sa.Column("broker_result_json", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("event_id", name="ux_ai_tm_journal_events_event_id"),
    )
    op.create_index(
        "ix_ai_tm_journal_events_shadow_ts",
        "ai_tm_journal_events",
        ["position_shadow_id", "ts"],
        unique=False,
    )
    op.create_index(
        "ix_ai_tm_journal_events_type",
        "ai_tm_journal_events",
        ["event_type"],
        unique=False,
    )

    op.create_table(
        "ai_tm_journal_postmortems",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("postmortem_id", sa.String(length=64), nullable=False),
        sa.Column("position_shadow_id", sa.String(length=64), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=False),
        sa.Column("realized_pnl_abs", sa.Float(), nullable=True),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("mfe_abs", sa.Float(), nullable=True),
        sa.Column("mfe_pct", sa.Float(), nullable=True),
        sa.Column("mae_abs", sa.Float(), nullable=True),
        sa.Column("mae_pct", sa.Float(), nullable=True),
        sa.Column("peak_price_while_open", sa.Float(), nullable=True),
        sa.Column("exit_quality", sa.String(length=24), nullable=False, server_default="UNKNOWN"),
        sa.Column("exit_quality_explanation", sa.Text(), nullable=True),
        sa.Column("forecast_vs_actual_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("postmortem_id", name="ux_ai_tm_journal_postmortems_postmortem_id"),
    )
    op.create_index(
        "ix_ai_tm_journal_postmortems_shadow",
        "ai_tm_journal_postmortems",
        ["position_shadow_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tm_journal_postmortems_shadow", table_name="ai_tm_journal_postmortems")
    op.drop_table("ai_tm_journal_postmortems")

    op.drop_index("ix_ai_tm_journal_events_type", table_name="ai_tm_journal_events")
    op.drop_index("ix_ai_tm_journal_events_shadow_ts", table_name="ai_tm_journal_events")
    op.drop_table("ai_tm_journal_events")

    op.drop_index("ix_ai_tm_journal_forecasts_shadow_ts", table_name="ai_tm_journal_forecasts")
    op.drop_table("ai_tm_journal_forecasts")

    op.drop_index("ix_ai_tm_manage_playbooks_enabled", table_name="ai_tm_manage_playbooks")
    op.drop_index("ix_ai_tm_manage_playbooks_scope", table_name="ai_tm_manage_playbooks")
    op.drop_table("ai_tm_manage_playbooks")

    op.drop_index("ix_ai_tm_position_shadows_last_seen", table_name="ai_tm_position_shadows")
    op.drop_index("ix_ai_tm_position_shadows_symbol_product", table_name="ai_tm_position_shadows")
    op.drop_index("ix_ai_tm_position_shadows_account_status", table_name="ai_tm_position_shadows")
    op.drop_table("ai_tm_position_shadows")

