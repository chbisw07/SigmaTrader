"""seed PVT-based builtin alert strategies

Revision ID: 0019
Revises: 0018
Create Date: 2025-12-10

"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
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
            "ST004-G PVT bullish correction",
            (
                "Price has sold off over the last month but PVT slope remains "
                "flat or rising, suggesting a bullish correction rather than "
                "distribution. Suitable for BUY / HOLD bias."
            ),
            "PERF_PCT(20, 1d) < -10 AND PVT_SLOPE(20, 1d) > 0",
        ),
        (
            "ST005-G PVT healthy uptrend",
            (
                "Price in an uptrend with PVT slope confirming positive volume "
                "flow. Suitable for HOLD / add-on entries on dips."
            ),
            "PRICE(1d) > MA(50, 1d) AND PVT_SLOPE(20, 1d) > 0",
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
                created_at=now,
                updated_at=now,
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM strategies "
            "WHERE is_builtin = 1 AND name LIKE 'ST004-G PVT bullish correction%' "
            "OR name LIKE 'ST005-G PVT healthy uptrend%';",
        ),
    )
