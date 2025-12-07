"""add market data tables for OHLCV storage

Revision ID: 0013
Revises: 0012
Create Date: 2025-12-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("instrument_token", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.UniqueConstraint(
            "symbol",
            "exchange",
            name="ux_market_instruments_symbol_exchange",
        ),
    )

    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column(
            "volume",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint(
            "symbol",
            "exchange",
            "timeframe",
            "ts",
            name="ux_candles_symbol_exchange_tf_ts",
        ),
    )
    op.create_index(
        "ix_candles_symbol_exchange_tf_ts",
        "candles",
        ["symbol", "exchange", "timeframe", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_candles_symbol_exchange_tf_ts", table_name="candles")
    op.drop_table("candles")
    op.drop_table("market_instruments")
