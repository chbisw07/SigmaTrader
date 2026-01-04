"""Add strategy deployment tables (config + runtime state).

Revision ID: 0045
Revises: 0044_repair_backtest_runs
Create Date: 2026-01-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044_repair_backtest_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "strategy_deployments" not in tables:
        op.create_table(
            "strategy_deployments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column(
                "execution_target",
                sa.String(length=16),
                nullable=False,
                server_default="PAPER",
            ),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "broker_name",
                sa.String(length=32),
                nullable=False,
                server_default="zerodha",
            ),
            sa.Column(
                "product",
                sa.String(length=16),
                nullable=False,
                server_default="CNC",
            ),
            sa.Column(
                "target_kind",
                sa.String(length=16),
                nullable=False,
                server_default="SYMBOL",
            ),
            sa.Column(
                "group_id",
                sa.Integer(),
                sa.ForeignKey("groups.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("exchange", sa.String(length=32)),
            sa.Column("symbol", sa.String(length=128)),
            sa.Column(
                "timeframe",
                sa.String(length=8),
                nullable=False,
                server_default="1d",
            ),
            sa.Column("config_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "kind IN ('STRATEGY', 'PORTFOLIO_STRATEGY')",
                name="ck_strategy_deployments_kind",
            ),
            sa.CheckConstraint(
                "execution_target IN ('PAPER', 'LIVE')",
                name="ck_strategy_deployments_execution_target",
            ),
            sa.CheckConstraint(
                "target_kind IN ('SYMBOL', 'GROUP')",
                name="ck_strategy_deployments_target_kind",
            ),
            sa.CheckConstraint(
                "timeframe IN ('1m','5m','15m','30m','1h','1d')",
                name="ck_strategy_deployments_timeframe",
            ),
            sa.CheckConstraint(
                "(target_kind = 'SYMBOL' AND symbol IS NOT NULL) OR "
                "(target_kind = 'GROUP' AND group_id IS NOT NULL)",
                name="ck_strategy_deployments_target_fields",
            ),
            sa.UniqueConstraint(
                "owner_id",
                "name",
                name="ux_strategy_deployments_owner_name",
            ),
        )
        inspector = sa.inspect(bind)

    existing_idx = {
        i.get("name") for i in inspector.get_indexes("strategy_deployments")
    }
    for name, cols in [
        ("ix_strategy_deployments_owner_id", ["owner_id"]),
        ("ix_strategy_deployments_kind", ["kind"]),
        ("ix_strategy_deployments_enabled", ["enabled"]),
        ("ix_strategy_deployments_execution_target", ["execution_target"]),
        ("ix_strategy_deployments_broker_name", ["broker_name"]),
        ("ix_strategy_deployments_group_id", ["group_id"]),
        ("ix_strategy_deployments_symbol", ["exchange", "symbol"]),
        ("ix_strategy_deployments_created_at", ["created_at"]),
    ]:
        if name not in existing_idx:
            op.create_index(name, "strategy_deployments", cols)

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "strategy_deployment_states" not in tables:
        op.create_table(
            "strategy_deployment_states",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "deployment_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="STOPPED",
            ),
            sa.Column("state_json", sa.Text()),
            sa.Column("last_evaluated_at", sa.DateTime(timezone=True)),
            sa.Column("next_evaluate_at", sa.DateTime(timezone=True)),
            sa.Column("last_error", sa.Text()),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("stopped_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('STOPPED', 'RUNNING', 'PAUSED', 'ERROR')",
                name="ck_strategy_deployment_states_status",
            ),
            sa.UniqueConstraint(
                "deployment_id",
                name="ux_strategy_deployment_states_deployment_id",
            ),
        )
        inspector = sa.inspect(bind)

    existing_idx = {
        i.get("name") for i in inspector.get_indexes("strategy_deployment_states")
    }
    for name, cols in [
        ("ix_strategy_deployment_states_deployment_id", ["deployment_id"]),
        ("ix_strategy_deployment_states_status", ["status"]),
        ("ix_strategy_deployment_states_last_evaluated_at", ["last_evaluated_at"]),
        ("ix_strategy_deployment_states_next_evaluate_at", ["next_evaluate_at"]),
    ]:
        if name not in existing_idx:
            op.create_index(name, "strategy_deployment_states", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "strategy_deployment_states" in tables:
        existing = {
            i.get("name") for i in inspector.get_indexes("strategy_deployment_states")
        }
        for name in [
            "ix_strategy_deployment_states_next_evaluate_at",
            "ix_strategy_deployment_states_last_evaluated_at",
            "ix_strategy_deployment_states_status",
            "ix_strategy_deployment_states_deployment_id",
        ]:
            if name in existing:
                op.drop_index(name, table_name="strategy_deployment_states")
        op.drop_table("strategy_deployment_states")

    inspector = sa.inspect(bind)
    if "strategy_deployments" not in inspector.get_table_names():
        return

    existing = {i.get("name") for i in inspector.get_indexes("strategy_deployments")}
    for name in [
        "ix_strategy_deployments_created_at",
        "ix_strategy_deployments_symbol",
        "ix_strategy_deployments_group_id",
        "ix_strategy_deployments_broker_name",
        "ix_strategy_deployments_execution_target",
        "ix_strategy_deployments_enabled",
        "ix_strategy_deployments_kind",
        "ix_strategy_deployments_owner_id",
    ]:
        if name in existing:
            op.drop_index(name, table_name="strategy_deployments")
    op.drop_table("strategy_deployments")
