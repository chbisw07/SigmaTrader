"""Add daily position snapshots.

Revision ID: 0030
Revises: 0029
Create Date: 2025-12-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("positions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "exchange",
                sa.String(length=32),
                nullable=False,
                server_default="NSE",
            )
        )
        batch_op.drop_constraint("ux_positions_symbol_product", type_="unique")
        batch_op.create_unique_constraint(
            "ux_positions_symbol_exchange_product",
            ["symbol", "exchange", "product"],
        )

    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column(
            "exchange",
            sa.String(length=32),
            nullable=False,
            server_default="NSE",
        ),
        sa.Column("product", sa.String(length=16), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_price", sa.Float()),
        sa.Column("close_price", sa.Float()),
        sa.Column("value", sa.Float()),
        sa.Column("m2m", sa.Float()),
        sa.Column("unrealised", sa.Float()),
        sa.Column("realised", sa.Float()),
        sa.Column("buy_qty", sa.Float()),
        sa.Column("buy_avg_price", sa.Float()),
        sa.Column("sell_qty", sa.Float()),
        sa.Column("sell_avg_price", sa.Float()),
        sa.Column("day_buy_qty", sa.Float()),
        sa.Column("day_buy_avg_price", sa.Float()),
        sa.Column("day_sell_qty", sa.Float()),
        sa.Column("day_sell_avg_price", sa.Float()),
        sa.UniqueConstraint(
            "as_of_date",
            "symbol",
            "exchange",
            "product",
            name="ux_position_snapshots_date_symbol_exchange_product",
        ),
    )
    op.create_index(
        "ix_position_snapshots_date_symbol",
        "position_snapshots",
        ["as_of_date", "symbol"],
    )
    op.create_index(
        "ix_position_snapshots_symbol_date",
        "position_snapshots",
        ["symbol", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_position_snapshots_symbol_date", table_name="position_snapshots")
    op.drop_index("ix_position_snapshots_date_symbol", table_name="position_snapshots")
    op.drop_table("position_snapshots")

    with op.batch_alter_table("positions") as batch_op:
        batch_op.drop_constraint("ux_positions_symbol_exchange_product", type_="unique")
        batch_op.create_unique_constraint(
            "ux_positions_symbol_product",
            ["symbol", "product"],
        )
        batch_op.drop_column("exchange")
