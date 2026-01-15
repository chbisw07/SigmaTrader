"""Add SigmaTrader-managed risk exits tables/fields.

Revision ID: 0052
Revises: 0051
Create Date: 2026-01-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    try:
        return table in inspector.get_table_names()
    except Exception:
        return False


def _has_column(inspector, table: str, name: str) -> bool:
    try:
        cols = inspector.get_columns(table)
    except Exception:
        return False
    return any(c.get("name") == name for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "orders"):
        if not _has_column(inspector, "orders", "risk_spec_json"):
            op.add_column("orders", sa.Column("risk_spec_json", sa.Text()))
        if not _has_column(inspector, "orders", "is_exit"):
            op.add_column(
                "orders",
                sa.Column(
                    "is_exit",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )

    if not _has_table(inspector, "managed_risk_positions"):
        op.create_table(
            "managed_risk_positions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "entry_order_id",
                sa.Integer(),
                sa.ForeignKey("orders.id", ondelete="CASCADE"),
                nullable=False,
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
                sa.String(length=32),
                nullable=False,
                server_default="NSE",
            ),
            sa.Column("product", sa.String(length=16), nullable=False),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column(
                "execution_target",
                sa.String(length=16),
                nullable=False,
                server_default="LIVE",
            ),
            sa.Column("risk_spec_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("entry_price", sa.Float(), nullable=False),
            sa.Column("stop_distance", sa.Float(), nullable=True),
            sa.Column("trail_distance", sa.Float(), nullable=True),
            sa.Column("activation_distance", sa.Float(), nullable=True),
            sa.Column("best_favorable_price", sa.Float(), nullable=False),
            sa.Column("trail_price", sa.Float(), nullable=True),
            sa.Column(
                "is_trailing_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("last_ltp", sa.Float(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="ACTIVE",
            ),
            sa.Column(
                "exit_order_id",
                sa.Integer(),
                sa.ForeignKey("orders.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("exit_reason", sa.String(length=16), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "entry_order_id",
                name="ux_managed_risk_positions_entry_order_id",
            ),
        )
        op.create_index(
            "ix_managed_risk_positions_status",
            "managed_risk_positions",
            ["status"],
        )
        op.create_index(
            "ix_managed_risk_positions_broker_symbol",
            "managed_risk_positions",
            ["broker_name", "symbol", "exchange", "product"],
        )
        op.create_index(
            "ix_managed_risk_positions_exit_order_id",
            "managed_risk_positions",
            ["exit_order_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "managed_risk_positions"):
        op.drop_index(
            "ix_managed_risk_positions_exit_order_id",
            table_name="managed_risk_positions",
        )
        op.drop_index(
            "ix_managed_risk_positions_broker_symbol",
            table_name="managed_risk_positions",
        )
        op.drop_index(
            "ix_managed_risk_positions_status",
            table_name="managed_risk_positions",
        )
        op.drop_table("managed_risk_positions")

    if _has_table(inspector, "orders"):
        if _has_column(inspector, "orders", "is_exit"):
            op.drop_column("orders", "is_exit")
        if _has_column(inspector, "orders", "risk_spec_json"):
            op.drop_column("orders", "risk_spec_json")
