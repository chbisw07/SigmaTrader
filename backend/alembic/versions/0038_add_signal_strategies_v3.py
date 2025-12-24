"""Add saved Signal Strategies (DSL V3) with versioning.

Revision ID: 0038
Revises: 0037
Create Date: 2025-12-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the Signal Strategy schema.

    SQLite DDL is non-transactional, so partial application can happen when a
    previous attempt failed mid-upgrade. This migration is intentionally
    idempotent so rerunning `alembic upgrade head` can converge the schema.
    """

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def has_table(name: str) -> bool:
        return name in inspector.get_table_names()

    def has_column(table: str, column: str) -> bool:
        return column in {c["name"] for c in inspector.get_columns(table)}

    if not has_table("signal_strategies"):
        op.create_table(
            "signal_strategies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "scope", sa.String(length=16), nullable=False, server_default="USER"
            ),
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("regimes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "latest_version", sa.Integer(), nullable=False, server_default="1"
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "scope IN ('USER', 'GLOBAL')", name="ck_signal_strategies_scope"
            ),
            sa.UniqueConstraint(
                "scope", "owner_id", "name", name="ux_signal_strategies_name"
            ),
        )
        # Refresh inspector cache after DDL.
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_signal_strategies_owner_updated",
        "signal_strategies",
        ["owner_id", "updated_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_signal_strategies_scope_updated",
        "signal_strategies",
        ["scope", "updated_at"],
        if_not_exists=True,
    )

    if not has_table("signal_strategy_versions"):
        op.create_table(
            "signal_strategy_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "strategy_id",
                sa.Integer(),
                sa.ForeignKey("signal_strategies.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("inputs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("variables_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("outputs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "compatibility_json", sa.Text(), nullable=False, server_default="{}"
            ),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "strategy_id",
                "version",
                name="ux_signal_strategy_versions_strategy_version",
            ),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_signal_strategy_versions_strategy",
        "signal_strategy_versions",
        ["strategy_id", "version"],
        if_not_exists=True,
    )

    if not has_column("alert_definitions", "signal_strategy_version_id"):
        op.add_column(
            "alert_definitions",
            sa.Column(
                "signal_strategy_version_id",
                sa.Integer(),
                sa.ForeignKey("signal_strategy_versions.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        inspector = sa.inspect(bind)

    if not has_column("alert_definitions", "signal_strategy_output"):
        op.add_column(
            "alert_definitions",
            sa.Column("signal_strategy_output", sa.String(length=64), nullable=True),
        )
        inspector = sa.inspect(bind)

    if not has_column("alert_definitions", "signal_strategy_params_json"):
        op.add_column(
            "alert_definitions",
            sa.Column(
                "signal_strategy_params_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_alert_definitions_strategy_version",
        "alert_definitions",
        ["signal_strategy_version_id"],
        if_not_exists=True,
    )

    if not has_column("screener_runs", "signal_strategy_version_id"):
        op.add_column(
            "screener_runs",
            sa.Column(
                "signal_strategy_version_id",
                sa.Integer(),
                sa.ForeignKey("signal_strategy_versions.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        inspector = sa.inspect(bind)

    if not has_column("screener_runs", "signal_strategy_output"):
        op.add_column(
            "screener_runs",
            sa.Column("signal_strategy_output", sa.String(length=64), nullable=True),
        )
        inspector = sa.inspect(bind)

    if not has_column("screener_runs", "signal_strategy_params_json"):
        op.add_column(
            "screener_runs",
            sa.Column(
                "signal_strategy_params_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
        )
        inspector = sa.inspect(bind)

    op.create_index(
        "ix_screener_runs_strategy_version",
        "screener_runs",
        ["signal_strategy_version_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_screener_runs_strategy_version", table_name="screener_runs")
    op.drop_column("screener_runs", "signal_strategy_params_json")
    op.drop_column("screener_runs", "signal_strategy_output")
    op.drop_column("screener_runs", "signal_strategy_version_id")

    op.drop_index(
        "ix_alert_definitions_strategy_version", table_name="alert_definitions"
    )
    op.drop_column("alert_definitions", "signal_strategy_params_json")
    op.drop_column("alert_definitions", "signal_strategy_output")
    op.drop_column("alert_definitions", "signal_strategy_version_id")

    op.drop_index(
        "ix_signal_strategy_versions_strategy",
        table_name="signal_strategy_versions",
    )
    op.drop_table("signal_strategy_versions")

    op.drop_index(
        "ix_signal_strategies_owner_updated",
        table_name="signal_strategies",
    )
    op.drop_index(
        "ix_signal_strategies_scope_updated",
        table_name="signal_strategies",
    )
    op.drop_table("signal_strategies")
