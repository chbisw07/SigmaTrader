"""Add alert_events table for v3 alerts.

Revision ID: 0026
Revises: 0025
Create Date: 2025-12-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "alert_definition_id",
            sa.Integer(),
            sa.ForeignKey("alert_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=64)),
        sa.Column("evaluation_cadence", sa.String(length=8)),
        sa.Column("reason", sa.Text()),
        sa.Column("snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("bar_time", sa.DateTime()),
    )
    op.create_index(
        "ix_alert_events_alert_time",
        "alert_events",
        ["alert_definition_id", "triggered_at"],
    )
    op.create_index(
        "ix_alert_events_symbol_time",
        "alert_events",
        ["symbol", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_events_symbol_time", table_name="alert_events")
    op.drop_index("ix_alert_events_alert_time", table_name="alert_events")
    op.drop_table("alert_events")
