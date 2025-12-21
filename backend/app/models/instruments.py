from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Security(Base):
    __tablename__ = "securities"

    __table_args__ = (
        UniqueConstraint("isin", name="ux_securities_isin"),
        Index("ix_securities_isin", "isin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ISIN is the stable cross-broker identifier (may be NULL for legacy rows).
    isin: Mapped[Optional[str]] = mapped_column(String(32))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class Listing(Base):
    __tablename__ = "listings"

    __table_args__ = (
        UniqueConstraint("exchange", "symbol", name="ux_listings_exchange_symbol"),
        Index("ix_listings_security_exchange", "security_id", "exchange"),
        Index("ix_listings_exchange_symbol", "exchange", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("securities.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Canonical exchange/symbol used across the app (groups, alerts, etc).
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class BrokerInstrument(Base):
    __tablename__ = "broker_instruments"

    __table_args__ = (
        UniqueConstraint(
            "broker_name",
            "instrument_token",
            name="ux_broker_instruments_broker_token",
        ),
        Index("ix_broker_instruments_broker_listing", "broker_name", "listing_id"),
        Index(
            "ix_broker_instruments_broker_exchange_symbol",
            "broker_name",
            "exchange",
            "broker_symbol",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )

    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    broker_symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_token: Mapped[str] = mapped_column(String(64), nullable=False)

    # Optional denormalized fields for convenience.
    isin: Mapped[Optional[str]] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["BrokerInstrument", "Listing", "Security"]
