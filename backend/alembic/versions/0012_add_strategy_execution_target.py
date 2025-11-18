"""Add execution_target and paper_poll_interval_sec to strategies.

Revision ID: 0012
Revises: 0011
Create Date: 2025-11-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

RevisionType = Union[str, None]

# revision identifiers, used by Alembic.
revision: RevisionType = "0012"
down_revision: RevisionType = "0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "strategies" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("strategies")}
    if "execution_target" not in columns:
        op.add_column(
            "strategies",
            sa.Column(
                "execution_target",
                sa.String(length=16),
                nullable=False,
                server_default="LIVE",
            ),
        )
    if "paper_poll_interval_sec" not in columns:
        op.add_column(
            "strategies",
            sa.Column("paper_poll_interval_sec", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "strategies" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("strategies")}
    if "paper_poll_interval_sec" in columns:
        op.drop_column("strategies", "paper_poll_interval_sec")
    if "execution_target" in columns:
        op.drop_column("strategies", "execution_target")
