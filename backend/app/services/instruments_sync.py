from __future__ import annotations

from datetime import timedelta
from threading import Event, Thread
from typing import Any, Iterable

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models import Listing, Security
from app.services.market_data import (
    MarketDataError,
    _get_kite_client,
    _get_or_create_listing,
    _invert_zerodha_symbol_map,
    _upsert_broker_instrument,
    listing_isin,
)
from app.services.system_events import record_system_event

_scheduler_started = False
_stop_event = Event()


def _iter_zerodha_instruments(
    db: Session,
    settings: Settings,
    *,
    exchanges: Iterable[str],
) -> Iterable[dict[str, Any]]:
    kite = _get_kite_client(db, settings)
    for exch in exchanges:
        try:
            rows = kite.instruments(str(exch).upper())
        except Exception:
            continue
        for row in rows:
            if isinstance(row, dict):
                yield row


def sync_zerodha_instrument_master(
    db: Session,
    settings: Settings,
    *,
    exchanges: Iterable[str] = ("NSE", "BSE"),
) -> dict[str, Any]:
    """Ingest Kite instrument master into canonical security/listing mapping."""

    inverse_map = _invert_zerodha_symbol_map()
    processed = 0
    upserted = 0

    for row in _iter_zerodha_instruments(db, settings, exchanges=exchanges):
        exch = str(row.get("exchange") or "").strip().upper()
        if exch not in {"NSE", "BSE"}:
            continue
        broker_symbol = str(row.get("tradingsymbol") or "").strip().upper()
        token = row.get("instrument_token")
        if not broker_symbol or token is None:
            continue

        isin_raw = row.get("isin")
        isin = (
            str(isin_raw).strip().upper()
            if isinstance(isin_raw, str) and isin_raw.strip()
            else None
        )
        name = str(row.get("name") or "").strip() or None

        canonical_symbol = inverse_map.get(exch, {}).get(broker_symbol, broker_symbol)

        listing = _get_or_create_listing(
            db,
            exchange=exch,
            symbol=canonical_symbol,
            isin=isin,
            name=name,
        )
        _upsert_broker_instrument(
            db,
            broker_name="zerodha",
            listing_id=listing.id,
            exchange=exch,
            broker_symbol=broker_symbol,
            instrument_token=str(token),
            isin=listing_isin(db, listing),
            active=True,
        )
        processed += 1
        upserted += 1

    db.commit()
    record_system_event(
        db,
        level="INFO",
        category="instruments",
        message="Zerodha instrument master synced",
        correlation_id=None,
        details={"broker": "zerodha", "processed": processed, "upserted": upserted},
    )
    return {"broker": "zerodha", "processed": processed, "upserted": upserted}


def sync_smartapi_instrument_master(
    db: Session,
    settings: Settings,
    *,
    url: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Ingest SmartAPI scrip master into canonical security/listing mapping.

    This endpoint does not require AngelOne authentication; the scrip master is
    a public dataset. We map into the canonical universe via ISIN when present.
    """

    master_url = (url or settings.smartapi_instrument_master_url or "").strip()
    if not master_url:
        raise RuntimeError("SmartAPI instrument master URL is not configured.")

    with httpx.Client(timeout=60) as client:
        resp = client.get(master_url)
        resp.raise_for_status()
        payload = resp.json()

    if not isinstance(payload, list):
        raise RuntimeError("Unexpected SmartAPI instrument master format.")

    processed = 0
    upserted = 0

    for row in payload:
        if limit is not None and processed >= limit:
            break
        if not isinstance(row, dict):
            continue

        exch_raw = row.get("exch_seg") or row.get("exchange")
        exch = str(exch_raw or "").strip().upper()
        if exch not in {"NSE", "BSE"}:
            continue

        broker_symbol = str(row.get("symbol") or row.get("tradingsymbol") or "").strip()
        token = row.get("token") or row.get("instrument_token")
        isin_raw = row.get("isin") or row.get("ISIN")
        isin = (
            str(isin_raw).strip().upper()
            if isinstance(isin_raw, str) and isin_raw.strip()
            else None
        )
        name = str(row.get("name") or "").strip() or None

        if not broker_symbol or token is None:
            continue

        canonical_symbol = broker_symbol.strip().upper()

        # If we already have a canonical listing for this ISIN+exchange (e.g.
        # from Zerodha), prefer that symbol to keep groups broker-agnostic.
        if isin:
            existing = (
                db.query(Listing)
                .join(Security, Security.id == Listing.security_id)
                .filter(
                    Security.isin == isin,
                    Listing.exchange == exch,
                )
                .order_by(Listing.updated_at.desc())
                .first()
            )
            if existing is not None:
                canonical_symbol = existing.symbol

        listing = _get_or_create_listing(
            db,
            exchange=exch,
            symbol=canonical_symbol,
            isin=isin,
            name=name,
        )
        _upsert_broker_instrument(
            db,
            broker_name="angelone",
            listing_id=listing.id,
            exchange=exch,
            broker_symbol=broker_symbol.strip().upper(),
            instrument_token=str(token),
            isin=listing_isin(db, listing),
            active=True,
        )
        processed += 1
        upserted += 1

    db.commit()
    record_system_event(
        db,
        level="INFO",
        category="instruments",
        message="SmartAPI instrument master synced",
        correlation_id=None,
        details={
            "broker": "angelone",
            "processed": processed,
            "upserted": upserted,
            "url": master_url,
        },
    )
    return {"broker": "angelone", "processed": processed, "upserted": upserted}


def sync_instrument_master_once() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        try:
            sync_zerodha_instrument_master(db, settings)
        except MarketDataError:
            return
        except Exception:
            return


def _loop() -> None:  # pragma: no cover
    settings = get_settings()
    interval = timedelta(
        hours=max(int(settings.instrument_master_sync_interval_hours), 1)
    )
    next_run = timedelta(seconds=5)
    _stop_event.wait(timeout=next_run.total_seconds())

    while not _stop_event.is_set():
        try:
            sync_instrument_master_once()
        except Exception:
            pass
        _stop_event.wait(timeout=interval.total_seconds())


def schedule_instrument_master_sync() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    thread = Thread(target=_loop, name="instrument-master-sync", daemon=True)
    thread.start()


__all__ = [
    "schedule_instrument_master_sync",
    "sync_zerodha_instrument_master",
    "sync_smartapi_instrument_master",
]
