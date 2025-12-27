"""Repair backtest_runs table (ensure present).

Revision ID: 0044
Revises: 0043_add_backtest_runs
Create Date: 2025-12-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043_add_backtest_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "backtest_runs" not in tables:
        op.create_table(
            "backtest_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="PENDING"
            ),
            sa.Column("title", sa.String(length=255)),
            sa.Column("config_json", sa.Text(), nullable=False),
            sa.Column("result_json", sa.Text()),
            sa.Column("error_message", sa.Text()),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)

    existing = {i.get("name") for i in inspector.get_indexes("backtest_runs")}
    for name, cols in [
        ("ix_backtest_runs_owner_id", ["owner_id"]),
        ("ix_backtest_runs_created_at", ["created_at"]),
        ("ix_backtest_runs_kind", ["kind"]),
        ("ix_backtest_runs_status", ["status"]),
    ]:
        if name not in existing:
            op.create_index(name, "backtest_runs", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "backtest_runs" not in inspector.get_table_names():
        return

    existing = {i.get("name") for i in inspector.get_indexes("backtest_runs")}
    for name in [
        "ix_backtest_runs_status",
        "ix_backtest_runs_kind",
        "ix_backtest_runs_created_at",
        "ix_backtest_runs_owner_id",
    ]:
        if name in existing:
            op.drop_index(name, table_name="backtest_runs")
    op.drop_table("backtest_runs")
