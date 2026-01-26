"""Add TradingView alert payload templates.

Revision ID: 0062
Revises: 0061
Create Date: 2026-01-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tradingview_alert_payload_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "config_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ux_tradingview_alert_payload_templates_name",
        "tradingview_alert_payload_templates",
        ["name"],
        unique=True,
    )
    op.create_index(
        "ix_tradingview_alert_payload_templates_updated_at",
        "tradingview_alert_payload_templates",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tradingview_alert_payload_templates_updated_at",
        table_name="tradingview_alert_payload_templates",
    )
    op.drop_index(
        "ux_tradingview_alert_payload_templates_name",
        table_name="tradingview_alert_payload_templates",
    )
    op.drop_table("tradingview_alert_payload_templates")

