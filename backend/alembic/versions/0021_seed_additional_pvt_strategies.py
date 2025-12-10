"""seed additional PVT-based builtin strategies

Revision ID: 0021
Revises: 0020
Create Date: 2025-12-10

"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
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
        sa.column("available_for_alert", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    now = datetime.now(UTC)

    presets = [
        (
            "ST006-G PVT bearish distribution",
            (
                "Price remains above the 50-day moving average but PVT slope "
                "has turned negative, suggesting distribution and weakening "
                "trend. Suitable for partial profit taking or tighter stops."
            ),
            "PRICE(1d) > MA(50, 1d) AND PVT_SLOPE(20, 1d) < 0",
        ),
        (
            "ST007-G PVT exhaustion after rally",
            (
                "Strong 3-month rally with RSI overbought and PVT slope "
                "rolling over. Suitable for taking profits or avoiding new "
                "longs."
            ),
            "PERF_PCT(60, 1d) > 25 AND RSI(14, 1d) > 70 AND PVT_SLOPE(20, 1d) < 0",
        ),
        (
            "ST008-G PVT-confirmed breakout",
            (
                "Price trading above 50-day moving average with strongly "
                "positive PVT slope. Suitable for buying strength or adding "
                "to existing positions."
            ),
            "PRICE(1d) > MA(50, 1d) AND PVT_SLOPE(20, 1d) > 5",
        ),
        (
            "ST009-G PVT oversold accumulation",
            (
                "Deep 3-month drawdown and oversold RSI while PVT slope is "
                "flat or rising, suggesting accumulation on weakness. "
                "Suitable for contrarian entries or reducing selling."
            ),
            "PERF_PCT(60, 1d) < -20 AND RSI(14, 1d) < 35 AND PVT_SLOPE(20, 1d) >= 0",
        ),
    ]

    for name, description, dsl in presets:
        conn.execute(
            sa.insert(strategies_table).values(
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
                available_for_alert=True,
                created_at=now,
                updated_at=now,
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM strategies "
            "WHERE is_builtin = 1 AND name LIKE 'ST006-G PVT bearish distribution%' "
            "OR name LIKE 'ST007-G PVT exhaustion after rally%' "
            "OR name LIKE 'ST008-G PVT-confirmed breakout%' "
            "OR name LIKE 'ST009-G PVT oversold accumulation%';",
        ),
    )
