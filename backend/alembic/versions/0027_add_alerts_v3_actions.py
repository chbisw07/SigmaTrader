"""Add action fields to v3 alert_definitions.

Revision ID: 0027
Revises: 0026
Create Date: 2025-12-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite requires batch mode for adding constraints reliably.
    with op.batch_alter_table("alert_definitions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "action_type",
                sa.String(length=16),
                nullable=False,
                server_default="ALERT_ONLY",
            )
        )
        batch_op.add_column(
            sa.Column(
                "action_params_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.create_check_constraint(
            "ck_alert_definitions_action_type",
            "action_type IN ('ALERT_ONLY', 'BUY', 'SELL')",
        )


def downgrade() -> None:
    with op.batch_alter_table("alert_definitions") as batch_op:
        batch_op.drop_constraint(
            "ck_alert_definitions_action_type",
            type_="check",
        )
        batch_op.drop_column("action_params_json")
        batch_op.drop_column("action_type")
