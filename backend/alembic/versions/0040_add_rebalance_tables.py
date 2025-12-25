"""Add portfolio rebalance schema (policies, schedules, runs, run orders).

Revision ID: 0040
Revises: 0039
Create Date: 2025-12-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply rebalance tables.

    SQLite DDL is non-transactional; keep this migration idempotent so reruns
    converge the schema.
    """

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def has_table(name: str) -> bool:
        return name in inspector.get_table_names()

    if not has_table("rebalance_policies"):
        op.create_table(
            "rebalance_policies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "group_id",
                sa.Integer(),
                sa.ForeignKey("groups.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "name", sa.String(length=255), nullable=False, server_default="default"
            ),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column(
                "broker_scope",
                sa.String(length=32),
                nullable=False,
                server_default="zerodha",
            ),
            sa.Column("policy_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "owner_id",
                "group_id",
                name="ux_rebalance_policies_owner_group",
            ),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_rebalance_policies_owner_id",
        "rebalance_policies",
        ["owner_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_rebalance_policies_group_id",
        "rebalance_policies",
        ["group_id"],
        if_not_exists=True,
    )

    if not has_table("rebalance_schedules"):
        op.create_table(
            "rebalance_schedules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "policy_id",
                sa.Integer(),
                sa.ForeignKey("rebalance_policies.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column("schedule_json", sa.Text(), nullable=True),
            sa.Column("next_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "policy_id",
                name="ux_rebalance_schedules_policy_id",
            ),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_rebalance_schedules_policy_id",
        "rebalance_schedules",
        ["policy_id"],
        if_not_exists=True,
    )

    if not has_table("rebalance_runs"):
        op.create_table(
            "rebalance_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "group_id",
                sa.Integer(),
                sa.ForeignKey("groups.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("broker_name", sa.String(length=32), nullable=False),
            sa.Column(
                "status", sa.String(length=16), nullable=False, server_default="CREATED"
            ),
            sa.Column(
                "mode", sa.String(length=16), nullable=False, server_default="MANUAL"
            ),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("policy_snapshot_json", sa.Text(), nullable=True),
            sa.Column("inputs_snapshot_json", sa.Text(), nullable=True),
            sa.Column("summary_json", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("executed_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "status IN ('CREATED', 'EXECUTED', 'FAILED')",
                name="ck_rebalance_runs_status",
            ),
            sa.CheckConstraint(
                "mode IN ('MANUAL', 'AUTO')",
                name="ck_rebalance_runs_mode",
            ),
            sa.UniqueConstraint(
                "owner_id",
                "idempotency_key",
                name="ux_rebalance_runs_owner_idempotency",
            ),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_rebalance_runs_owner_id",
        "rebalance_runs",
        ["owner_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_rebalance_runs_group_id",
        "rebalance_runs",
        ["group_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_rebalance_runs_group_broker_time",
        "rebalance_runs",
        ["group_id", "broker_name", "created_at"],
        if_not_exists=True,
    )

    if not has_table("rebalance_run_orders"):
        op.create_table(
            "rebalance_run_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "run_id",
                sa.Integer(),
                sa.ForeignKey("rebalance_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "order_id",
                sa.Integer(),
                sa.ForeignKey("orders.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("exchange", sa.String(length=32), nullable=True),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("estimated_price", sa.Float(), nullable=True),
            sa.Column("estimated_notional", sa.Float(), nullable=True),
            sa.Column("target_weight", sa.Float(), nullable=True),
            sa.Column("live_weight", sa.Float(), nullable=True),
            sa.Column("drift", sa.Float(), nullable=True),
            sa.Column("current_value", sa.Float(), nullable=True),
            sa.Column("desired_value", sa.Float(), nullable=True),
            sa.Column("delta_value", sa.Float(), nullable=True),
            sa.Column("scale", sa.Float(), nullable=True),
            sa.Column("reason_json", sa.Text(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="PROPOSED",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_rebalance_run_orders_run_id",
        "rebalance_run_orders",
        ["run_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_rebalance_run_orders_order_id",
        "rebalance_run_orders",
        ["order_id"],
        if_not_exists=True,
    )


def downgrade() -> None:  # pragma: no cover
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def has_table(name: str) -> bool:
        return name in inspector.get_table_names()

    if has_table("rebalance_run_orders"):
        op.drop_table("rebalance_run_orders")
        inspector = sa.inspect(bind)
    if has_table("rebalance_runs"):
        op.drop_table("rebalance_runs")
        inspector = sa.inspect(bind)
    if has_table("rebalance_schedules"):
        op.drop_table("rebalance_schedules")
        inspector = sa.inspect(bind)
    if has_table("rebalance_policies"):
        op.drop_table("rebalance_policies")
