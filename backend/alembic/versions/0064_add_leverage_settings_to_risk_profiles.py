"""Add leverage settings to risk profiles.

Revision ID: 0064
Revises: 0063
Create Date: 2026-01-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_profiles", sa.Column("leverage_mode", sa.String(length=16), nullable=True))
    op.add_column(
        "risk_profiles",
        sa.Column("max_effective_leverage", sa.Float(), nullable=True),
    )
    op.add_column(
        "risk_profiles",
        sa.Column("max_margin_used_pct", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_profiles", "max_margin_used_pct")
    op.drop_column("risk_profiles", "max_effective_leverage")
    op.drop_column("risk_profiles", "leverage_mode")

