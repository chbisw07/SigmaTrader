"""Add broker-aware targeting fields to alerts v3.

Revision ID: 0034
Revises: 0033
Create Date: 2025-12-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_definitions",
        sa.Column(
            "broker_name",
            sa.String(length=32),
            nullable=False,
            server_default="zerodha",
        ),
    )
    op.add_column(
        "alert_definitions",
        sa.Column("symbol", sa.String(length=128), nullable=True),
    )

    # Backfill v3 SYMBOL alerts to use the new `symbol` column while keeping
    # target_ref as the legacy/compat storage for the same value.
    op.execute(
        "UPDATE alert_definitions SET symbol = target_ref "
        "WHERE target_kind = 'SYMBOL' AND (symbol IS NULL OR symbol = '')"
    )

    # Normalize HOLDINGS alerts: target_ref should be stable ('HOLDINGS') and
    # broker is expressed via broker_name.
    op.execute(
        "UPDATE alert_definitions SET target_ref = 'HOLDINGS', exchange = NULL "
        "WHERE target_kind = 'HOLDINGS'"
    )

    # Replace the legacy index with a broker-aware one.
    op.drop_index("ix_alert_definitions_user_target", table_name="alert_definitions")
    op.create_index(
        "ix_alert_definitions_user_broker_target",
        "alert_definitions",
        ["user_id", "broker_name", "target_kind", "target_ref"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_alert_definitions_user_broker_target", table_name="alert_definitions"
    )
    op.create_index(
        "ix_alert_definitions_user_target",
        "alert_definitions",
        ["user_id", "target_kind", "target_ref"],
    )

    # Restore the legacy HOLDINGS discriminator.
    op.execute(
        "UPDATE alert_definitions SET target_ref = 'ZERODHA' "
        "WHERE target_kind = 'HOLDINGS'"
    )

    op.drop_column("alert_definitions", "symbol")
    op.drop_column("alert_definitions", "broker_name")
