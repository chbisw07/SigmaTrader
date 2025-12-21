from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import BrokerInstrument, Listing


def resolve_broker_instrument_for_listing(
    db: Session,
    *,
    broker_name: str,
    exchange: str,
    symbol: str,
) -> Optional[BrokerInstrument]:
    broker = (broker_name or "").strip().lower()
    exch = (exchange or "NSE").strip().upper()
    sym = (symbol or "").strip().upper()
    if not sym:
        return None

    listing: Listing | None = (
        db.query(Listing)
        .filter(
            Listing.exchange == exch,
            Listing.symbol == sym,
            Listing.active.is_(True),
        )
        .one_or_none()
    )
    if listing is None:
        return None

    bi: BrokerInstrument | None = (
        db.query(BrokerInstrument)
        .filter(
            BrokerInstrument.broker_name == broker,
            BrokerInstrument.listing_id == listing.id,
            BrokerInstrument.active.is_(True),
        )
        .order_by(BrokerInstrument.updated_at.desc())
        .first()
    )
    return bi


def resolve_listing_for_broker_symbol(
    db: Session,
    *,
    broker_name: str,
    exchange: str,
    broker_symbol: str,
) -> Optional[Listing]:
    broker = (broker_name or "").strip().lower()
    exch = (exchange or "NSE").strip().upper()
    bsym = (broker_symbol or "").strip().upper()
    if not bsym:
        return None

    bi: BrokerInstrument | None = (
        db.query(BrokerInstrument)
        .filter(
            BrokerInstrument.broker_name == broker,
            BrokerInstrument.exchange == exch,
            BrokerInstrument.broker_symbol == bsym,
            BrokerInstrument.active.is_(True),
        )
        .order_by(BrokerInstrument.updated_at.desc())
        .first()
    )
    if bi is None:
        return None
    return db.get(Listing, bi.listing_id)


def resolve_broker_symbol_and_token(
    db: Session,
    *,
    broker_name: str,
    exchange: str,
    symbol: str,
) -> Optional[Tuple[str, str]]:
    bi = resolve_broker_instrument_for_listing(
        db,
        broker_name=broker_name,
        exchange=exchange,
        symbol=symbol,
    )
    if bi is None:
        return None
    return bi.broker_symbol, bi.instrument_token


__all__ = [
    "resolve_broker_instrument_for_listing",
    "resolve_listing_for_broker_symbol",
    "resolve_broker_symbol_and_token",
]
