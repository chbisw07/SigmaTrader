"""Add market calendar table (v3).

Revision ID: 0049
Revises: 0048
Create Date: 2026-01-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "market_calendar" in inspector.get_table_names():
        return

    op.create_table(
        "market_calendar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column(
            "session_type",
            sa.String(length=32),
            nullable=False,
            server_default="NORMAL",
        ),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "session_type IN ("
            "'NORMAL','CLOSED','SETTLEMENT_ONLY','HALF_DAY','SPECIAL'"
            ")",
            name="ck_market_calendar_session_type",
        ),
        sa.UniqueConstraint(
            "date", "exchange", name="ux_market_calendar_date_exchange"
        ),
    )
    op.create_index(
        "ix_market_calendar_exchange_date", "market_calendar", ["exchange", "date"]
    )
    op.create_index("ix_market_calendar_date", "market_calendar", ["date"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "market_calendar" not in inspector.get_table_names():
        return
    op.drop_index("ix_market_calendar_date", table_name="market_calendar")
    op.drop_index("ix_market_calendar_exchange_date", table_name="market_calendar")
    op.drop_table("market_calendar")
