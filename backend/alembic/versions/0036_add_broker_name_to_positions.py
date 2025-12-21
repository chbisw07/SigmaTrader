"""Add broker_name scoping to positions and position snapshots.

Revision ID: 0036
Revises: 0035
Create Date: 2025-12-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("positions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "broker_name",
                sa.String(length=32),
                nullable=False,
                server_default="zerodha",
            )
        )
        batch_op.drop_constraint(
            "ux_positions_symbol_exchange_product",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "ux_positions_broker_symbol_exchange_product",
            ["broker_name", "symbol", "exchange", "product"],
        )

    op.create_index(
        "ix_positions_broker_symbol",
        "positions",
        ["broker_name", "symbol"],
    )

    with op.batch_alter_table("position_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column(
                "broker_name",
                sa.String(length=32),
                nullable=False,
                server_default="zerodha",
            )
        )
        batch_op.drop_constraint(
            "ux_position_snapshots_date_symbol_exchange_product",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "ux_position_snapshots_broker_date_symbol_exchange_product",
            ["broker_name", "as_of_date", "symbol", "exchange", "product"],
        )

    op.drop_index("ix_position_snapshots_date_symbol", table_name="position_snapshots")
    op.drop_index("ix_position_snapshots_symbol_date", table_name="position_snapshots")
    op.create_index(
        "ix_position_snapshots_broker_date_symbol",
        "position_snapshots",
        ["broker_name", "as_of_date", "symbol"],
    )
    op.create_index(
        "ix_position_snapshots_broker_symbol_date",
        "position_snapshots",
        ["broker_name", "symbol", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_snapshots_broker_symbol_date",
        table_name="position_snapshots",
    )
    op.drop_index(
        "ix_position_snapshots_broker_date_symbol",
        table_name="position_snapshots",
    )
    op.create_index(
        "ix_position_snapshots_symbol_date",
        "position_snapshots",
        ["symbol", "as_of_date"],
    )
    op.create_index(
        "ix_position_snapshots_date_symbol",
        "position_snapshots",
        ["as_of_date", "symbol"],
    )

    with op.batch_alter_table("position_snapshots") as batch_op:
        batch_op.drop_constraint(
            "ux_position_snapshots_broker_date_symbol_exchange_product",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "ux_position_snapshots_date_symbol_exchange_product",
            ["as_of_date", "symbol", "exchange", "product"],
        )
        batch_op.drop_column("broker_name")

    op.drop_index("ix_positions_broker_symbol", table_name="positions")
    with op.batch_alter_table("positions") as batch_op:
        batch_op.drop_constraint(
            "ux_positions_broker_symbol_exchange_product",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "ux_positions_symbol_exchange_product",
            ["symbol", "exchange", "product"],
        )
        batch_op.drop_column("broker_name")
