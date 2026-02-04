"""Add managed-risk defaults to risk profiles.

Revision ID: 0068
Revises: 0067
Create Date: 2026-02-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_profiles",
        sa.Column(
            "managed_risk_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "trailing_stop_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "trail_activation_atr",
            sa.Float(),
            nullable=False,
            server_default=sa.text("2.5"),
        ),
    )
    op.add_column(
        "risk_profiles",
        sa.Column(
            "trail_activation_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("3.0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("risk_profiles", "trail_activation_pct")
    op.drop_column("risk_profiles", "trail_activation_atr")
    op.drop_column("risk_profiles", "trailing_stop_enabled")
    op.drop_column("risk_profiles", "managed_risk_enabled")

