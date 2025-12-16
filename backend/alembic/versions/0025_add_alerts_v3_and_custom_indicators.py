"""Add alert_definitions and custom_indicators.

Revision ID: 0025
Revises: 0024
Create Date: 2025-12-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "target_kind", sa.String(length=16), nullable=False, server_default="SYMBOL"
        ),
        sa.Column("target_ref", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=32)),
        sa.Column(
            "evaluation_cadence",
            sa.String(length=8),
            nullable=False,
            server_default="1m",
        ),
        sa.Column("variables_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("condition_dsl", sa.Text(), nullable=False),
        sa.Column("condition_ast_json", sa.Text()),
        sa.Column(
            "trigger_mode",
            sa.String(length=32),
            nullable=False,
            server_default="ONCE_PER_BAR",
        ),
        sa.Column("throttle_seconds", sa.Integer()),
        sa.Column(
            "only_market_hours",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_evaluated_at", sa.DateTime()),
        sa.Column("last_triggered_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "target_kind IN ('SYMBOL', 'HOLDINGS', 'GROUP')",
            name="ck_alert_definitions_target_kind",
        ),
        sa.CheckConstraint(
            "trigger_mode IN ('ONCE', 'ONCE_PER_BAR', 'EVERY_TIME')",
            name="ck_alert_definitions_trigger_mode",
        ),
    )
    op.create_index(
        "ix_alert_definitions_user_enabled",
        "alert_definitions",
        ["user_id", "enabled"],
    )
    op.create_index(
        "ix_alert_definitions_user_target",
        "alert_definitions",
        ["user_id", "target_kind", "target_ref"],
    )

    op.create_table(
        "custom_indicators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("params_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("body_dsl", sa.Text(), nullable=False),
        sa.Column("body_ast_json", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="ux_custom_indicators_user_name"),
    )
    op.create_index(
        "ix_custom_indicators_user_enabled",
        "custom_indicators",
        ["user_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_custom_indicators_user_enabled", table_name="custom_indicators")
    op.drop_table("custom_indicators")

    op.drop_index("ix_alert_definitions_user_target", table_name="alert_definitions")
    op.drop_index("ix_alert_definitions_user_enabled", table_name="alert_definitions")
    op.drop_table("alert_definitions")
