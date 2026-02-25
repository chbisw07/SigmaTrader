"""Add no_trade_rules to risk_global_config.

Revision ID: 0079
Revises: 0078
Create Date: 2026-02-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_global_config", sa.Column("no_trade_rules", sa.Text()))


def downgrade() -> None:
    op.drop_column("risk_global_config", "no_trade_rules")

