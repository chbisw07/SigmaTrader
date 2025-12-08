"""seed a small set of builtin alert strategies

Revision ID: 0017
Revises: 0016
Create Date: 2025-12-08

"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    strategies_table = sa.table(
        "strategies",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("execution_mode", sa.String),
        sa.column("execution_target", sa.String),
        sa.column("paper_poll_interval_sec", sa.Integer),
        sa.column("enabled", sa.Boolean),
        sa.column("scope", sa.String),
        sa.column("dsl_expression", sa.Text),
        sa.column("expression_json", sa.Text),
        sa.column("is_builtin", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    now = datetime.now(UTC)

    presets = [
        (
            "ST001-G RSI overbought with trend filter",
            (
                "Daily RSI(14) > 80 with price above 50-day SMA "
                "and low 50-day volatility."
            ),
            (
                "(RSI(14, 1d) > 80) AND (PRICE(1d) > SMA(50, 1d)) "
                "AND (VOLATILITY(50, 1d) < 2.5)"
            ),
        ),
        (
            "ST002-G Bullish MA crossover",
            ("20-day SMA crossing above 50-day SMA with price above " "200-day SMA."),
            ("(SMA(20, 1d) CROSS_ABOVE SMA(50, 1d)) " "AND (PRICE(1d) > SMA(200, 1d))"),
        ),
        (
            "ST003-G Intraday pullback in daily uptrend",
            (
                "15m price below 20-period SMA while daily price is above "
                "50-day SMA and 15m RSI(14) < 40."
            ),
            (
                "(PRICE(15m) < SMA(20, 15m)) AND (PRICE(1d) > SMA(50, 1d)) "
                "AND (RSI(14, 15m) < 40)"
            ),
        ),
    ]

    for name, description, dsl in presets:
        conn.execute(
            sa.insert(strategies_table).values(
                # id is omitted so SQLite autoincrements it.
                name=name,
                description=description,
                execution_mode="MANUAL",
                execution_target="LIVE",
                paper_poll_interval_sec=None,
                enabled=True,
                scope="GLOBAL",
                dsl_expression=dsl,
                expression_json=None,
                is_builtin=True,
                created_at=now,
                updated_at=now,
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM strategies WHERE is_builtin = 1 AND name LIKE 'ST00%';",
        ),
    )
