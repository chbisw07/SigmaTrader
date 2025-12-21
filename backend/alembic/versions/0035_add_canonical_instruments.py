"""Add canonical instruments (security/listing) and broker instrument mapping.

Revision ID: 0035
Revises: 0034
Create Date: 2025-12-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "securities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
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
        sa.UniqueConstraint("isin", name="ux_securities_isin"),
    )
    op.create_index("ix_securities_isin", "securities", ["isin"])

    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "security_id",
            sa.Integer(),
            sa.ForeignKey("securities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
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
        sa.UniqueConstraint(
            "exchange",
            "symbol",
            name="ux_listings_exchange_symbol",
        ),
    )
    op.create_index(
        "ix_listings_security_exchange",
        "listings",
        ["security_id", "exchange"],
    )
    op.create_index(
        "ix_listings_exchange_symbol",
        "listings",
        ["exchange", "symbol"],
    )

    op.create_table(
        "broker_instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "listing_id",
            sa.Integer(),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("broker_symbol", sa.String(length=128), nullable=False),
        sa.Column("instrument_token", sa.String(length=64), nullable=False),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
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
        sa.UniqueConstraint(
            "broker_name",
            "instrument_token",
            name="ux_broker_instruments_broker_token",
        ),
    )
    op.create_index(
        "ix_broker_instruments_broker_listing",
        "broker_instruments",
        ["broker_name", "listing_id"],
    )
    op.create_index(
        "ix_broker_instruments_broker_exchange_symbol",
        "broker_instruments",
        ["broker_name", "exchange", "broker_symbol"],
    )

    # Best-effort backfill from legacy market_instruments cache. These rows do
    # not include ISIN; we still create a canonical listing and map a Zerodha
    # broker instrument token so existing market data continues to work.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT symbol, exchange, instrument_token, name, active "
            "FROM market_instruments"
        )
    ).fetchall()

    for symbol, exchange, token, name, active in rows:
        exch = str(exchange).upper()
        sym = str(symbol).upper()
        token_str = str(token)

        listing_id = conn.execute(
            sa.text("SELECT id FROM listings WHERE exchange=:e AND symbol=:s"),
            {"e": exch, "s": sym},
        ).scalar()
        if listing_id is None:
            conn.execute(
                sa.text(
                    "INSERT INTO listings(exchange, symbol, name, active) "
                    "VALUES (:e, :s, :n, :a)"
                ),
                {"e": exch, "s": sym, "n": name, "a": 1 if active else 0},
            )
            listing_id = conn.execute(
                sa.text("SELECT id FROM listings WHERE exchange=:e AND symbol=:s"),
                {"e": exch, "s": sym},
            ).scalar()

        if listing_id is None:
            continue

        existing = conn.execute(
            sa.text(
                "SELECT id FROM broker_instruments "
                "WHERE broker_name='zerodha' AND instrument_token=:t"
            ),
            {"t": token_str},
        ).scalar()
        if existing is None:
            conn.execute(
                sa.text(
                    (
                        "INSERT INTO broker_instruments("
                        "listing_id, broker_name, exchange, broker_symbol, "
                        "instrument_token, active"
                        ") VALUES (:lid, 'zerodha', :e, :bs, :t, :a)"
                    )
                ),
                {
                    "lid": int(listing_id),
                    "e": exch,
                    "bs": sym,
                    "t": token_str,
                    "a": 1 if active else 0,
                },
            )


def downgrade() -> None:
    op.drop_index(
        "ix_broker_instruments_broker_exchange_symbol", table_name="broker_instruments"
    )
    op.drop_index(
        "ix_broker_instruments_broker_listing", table_name="broker_instruments"
    )
    op.drop_table("broker_instruments")

    op.drop_index("ix_listings_exchange_symbol", table_name="listings")
    op.drop_index("ix_listings_security_exchange", table_name="listings")
    op.drop_table("listings")

    op.drop_index("ix_securities_isin", table_name="securities")
    op.drop_table("securities")
