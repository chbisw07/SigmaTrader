"""add indicator_rules table and alert source/rule_id

Revision ID: 0014
Revises: 0013
Create Date: 2025-12-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "sqlite"

    op.create_table(
        "indicator_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=True),
        sa.Column("universe", sa.String(length=32), nullable=True),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column(
            "timeframe",
            sa.String(length=8),
            nullable=False,
            server_default="1d",
        ),
        sa.Column(
            "logic",
            sa.String(length=8),
            nullable=False,
            server_default="AND",
        ),
        sa.Column("conditions_json", sa.Text(), nullable=False),
        sa.Column(
            "trigger_mode",
            sa.String(length=32),
            nullable=False,
            server_default="ONCE",
        ),
        sa.Column(
            "action_type",
            sa.String(length=32),
            nullable=False,
            server_default="ALERT_ONLY",
        ),
        sa.Column(
            "action_params_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_indicator_rules_user_symbol",
        "indicator_rules",
        ["user_id", "symbol"],
    )
    op.create_index(
        "ix_indicator_rules_user_timeframe",
        "indicator_rules",
        ["user_id", "timeframe"],
    )

    # Extend alerts with source and rule_id
    op.add_column(
        "alerts",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="TRADINGVIEW",
        ),
    )
    op.add_column(
        "alerts",
        sa.Column("rule_id", sa.Integer(), nullable=True),
    )
    if dialect_name != "sqlite":
        op.create_foreign_key(
            "fk_alerts_rule_id_indicator_rules",
            "alerts",
            "indicator_rules",
            ["rule_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "sqlite"

    if dialect_name != "sqlite":
        op.drop_constraint(
            "fk_alerts_rule_id_indicator_rules",
            "alerts",
            type_="foreignkey",
        )
    op.drop_column("alerts", "rule_id")
    op.drop_column("alerts", "source")

    op.drop_index("ix_indicator_rules_user_timeframe", table_name="indicator_rules")
    op.drop_index("ix_indicator_rules_user_symbol", table_name="indicator_rules")
    op.drop_table("indicator_rules")
