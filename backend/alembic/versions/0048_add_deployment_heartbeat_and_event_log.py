"""Add deployment heartbeat fields + event journal table (v3).

Revision ID: 0048
Revises: 0047
Create Date: 2026-01-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, name: str) -> bool:
    try:
        cols = inspector.get_columns(table)
    except Exception:
        return False
    return any(c.get("name") == name for c in cols)


def _index_names(inspector, table: str) -> set[str]:
    try:
        return {str(i.get("name") or "") for i in inspector.get_indexes(table)}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "strategy_deployment_states" in inspector.get_table_names():
        for name, col in [
            ("last_eval_at", sa.Column("last_eval_at", sa.DateTime(timezone=True))),
            (
                "last_eval_bar_end_ts",
                sa.Column("last_eval_bar_end_ts", sa.DateTime(timezone=True)),
            ),
            ("runtime_state", sa.Column("runtime_state", sa.String(length=32))),
            ("last_decision", sa.Column("last_decision", sa.String(length=32))),
            (
                "last_decision_reason",
                sa.Column("last_decision_reason", sa.String(length=255)),
            ),
            ("next_eval_at", sa.Column("next_eval_at", sa.DateTime(timezone=True))),
        ]:
            if not _has_column(inspector, "strategy_deployment_states", name):
                op.add_column("strategy_deployment_states", col)

        inspector = sa.inspect(bind)
        existing = _index_names(inspector, "strategy_deployment_states")
        for idx_name, cols in [
            ("ix_strategy_deployment_states_last_eval_at", ["last_eval_at"]),
            ("ix_strategy_deployment_states_next_eval_at", ["next_eval_at"]),
        ]:
            if idx_name not in existing:
                op.create_index(idx_name, "strategy_deployment_states", cols)

    inspector = sa.inspect(bind)
    if "strategy_deployment_event_logs" not in inspector.get_table_names():
        op.create_table(
            "strategy_deployment_event_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "deployment_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "job_id",
                sa.Integer(),
                sa.ForeignKey("strategy_deployment_jobs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

        op.create_index(
            "ix_strategy_deployment_event_logs_deployment_id",
            "strategy_deployment_event_logs",
            ["deployment_id"],
        )
        op.create_index(
            "ix_strategy_deployment_event_logs_created_at",
            "strategy_deployment_event_logs",
            ["created_at"],
        )
        op.create_index(
            "ix_strategy_deployment_event_logs_kind",
            "strategy_deployment_event_logs",
            ["kind"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "strategy_deployment_event_logs" in inspector.get_table_names():
        op.drop_index(
            "ix_strategy_deployment_event_logs_kind",
            table_name="strategy_deployment_event_logs",
        )
        op.drop_index(
            "ix_strategy_deployment_event_logs_created_at",
            table_name="strategy_deployment_event_logs",
        )
        op.drop_index(
            "ix_strategy_deployment_event_logs_deployment_id",
            table_name="strategy_deployment_event_logs",
        )
        op.drop_table("strategy_deployment_event_logs")

    inspector = sa.inspect(bind)
    if "strategy_deployment_states" in inspector.get_table_names():
        existing = _index_names(inspector, "strategy_deployment_states")
        for idx_name in [
            "ix_strategy_deployment_states_last_eval_at",
            "ix_strategy_deployment_states_next_eval_at",
        ]:
            if idx_name in existing:
                op.drop_index(idx_name, table_name="strategy_deployment_states")

        for col in [
            "next_eval_at",
            "last_decision_reason",
            "last_decision",
            "runtime_state",
            "last_eval_bar_end_ts",
            "last_eval_at",
        ]:
            if _has_column(inspector, "strategy_deployment_states", col):
                op.drop_column("strategy_deployment_states", col)
