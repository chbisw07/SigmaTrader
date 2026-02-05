from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from app.clients import AngelOneClient, ZerodhaClient
from app.models import Position, PositionSnapshot
from app.services.broker_instruments import resolve_listing_for_broker_symbol


def _as_float(value: object, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _canon_symbol(sym: str) -> str:
    """Return a canonical symbol key (upper + alphanumerics only)."""

    sym_u = sym.strip().upper()
    return "".join(ch for ch in sym_u if ch.isalnum())


def _as_of_date_ist(now_utc: datetime) -> date:
    # IST is the market session timezone for Zerodha (India).
    try:
        from zoneinfo import ZoneInfo

        return now_utc.astimezone(ZoneInfo("Asia/Kolkata")).date()
    except Exception:
        # Fallback: treat local timezone as IST if zoneinfo isn't available.
        return now_utc.date()


def sync_positions_from_zerodha(db: Session, client: ZerodhaClient) -> int:
    """Fetch positions from Zerodha and cache them in the local positions table.

    We use:
    - `net` for the current open positions table (`positions`)
    - `day` for the daily snapshots (`position_snapshots`) so closed intraday
      trades (net qty = 0) still appear in the UI when "include zero qty" is on.
    """

    payload: Dict[str, object] = client.list_positions()
    net: List[Dict[str, object]] = []
    net_raw = payload.get("net")
    if isinstance(net_raw, list):
        net = [entry for entry in net_raw if isinstance(entry, dict)]

    day: List[Dict[str, object]] = []
    day_raw = payload.get("day")
    if isinstance(day_raw, list):
        day = [entry for entry in day_raw if isinstance(entry, dict)]

    broker_name = "zerodha"
    # Clear existing positions for a simple cache refresh (scoped by broker).
    db.query(Position).filter(Position.broker_name == broker_name).delete()

    updated = 0  # snapshot rows inserted
    now = datetime.now(UTC)
    as_of = _as_of_date_ist(now)

    # Replace any previously captured snapshot for this day (scoped by broker).
    db.query(PositionSnapshot).filter(
        PositionSnapshot.broker_name == broker_name,
        PositionSnapshot.as_of_date == as_of,
    ).delete()

    snapshot_rows = day if day else net

    # Best-effort: fetch holdings so we can attach cost-basis avg price for
    # delivery sells (CNC) where positions payload often lacks buy_price.
    holdings_avg: dict[tuple[str, str], float] = {}
    holdings_qty: dict[tuple[str, str], float] = {}
    instruments: list[tuple[str, str]] = []
    try:
        holdings = client.list_holdings()
        for h in holdings:
            sym = h.get("tradingsymbol")
            exch = h.get("exchange") or "NSE"
            avg = _as_float(h.get("average_price"))
            if isinstance(sym, str) and isinstance(exch, str) and avg is not None:
                sym_raw = sym
                sym_u = sym_raw.strip().upper()
                sym_key = _canon_symbol(sym_raw)
                exch_u = exch.strip().upper()
                holdings_avg[(exch_u, sym_key)] = float(avg)
                qty = _as_float(h.get("quantity"))
                if qty is not None:
                    holdings_qty[(exch_u, sym_key)] = float(qty)
                # Keep original symbol for LTP lookups.
                instruments.append((exch_u, sym_u))
    except Exception:
        holdings_avg = {}
        holdings_qty = {}

    for entry in snapshot_rows:
        sym = entry.get("tradingsymbol")
        exch = entry.get("exchange") or "NSE"
        if isinstance(sym, str) and isinstance(exch, str):
            instruments.append((exch.strip().upper(), sym.strip().upper()))

    ltp_map: dict[tuple[str, str], dict[str, float | None]] = {}
    try:
        uniq = sorted(set(instruments))
        ltp_map = client.get_ltp_bulk(uniq)
    except Exception:
        ltp_map = {}

    # Open positions cache (net only).
    for entry in net:
        symbol = entry.get("tradingsymbol")
        exchange = entry.get("exchange") or "NSE"
        product = entry.get("product")
        quantity = _as_float(entry.get("quantity", 0), 0.0)
        avg_price = _as_float(entry.get("average_price", 0), 0.0)
        pnl = _as_float(entry.get("pnl", 0), 0.0)

        if (
            not isinstance(symbol, str)
            or not isinstance(exchange, str)
            or not isinstance(product, str)
        ):
            continue

        qty_f = float(quantity or 0.0)
        avg_price_f = float(avg_price or 0.0)
        pnl_f = float(pnl or 0.0)

        exch_u = exchange.strip().upper()
        symbol_u = symbol.strip().upper()

        position = Position(
            broker_name=broker_name,
            symbol=symbol_u,
            exchange=exch_u,
            product=product,
            qty=qty_f,
            avg_price=avg_price_f,
            pnl=pnl_f,
            last_updated=now,
        )
        db.add(position)

    # Daily snapshot rows (prefer `day`, fallback to `net`).
    for entry in snapshot_rows:
        symbol = entry.get("tradingsymbol")
        exchange = entry.get("exchange") or "NSE"
        product = entry.get("product")
        quantity = _as_float(entry.get("quantity", 0), 0.0)
        avg_price = _as_float(entry.get("average_price", 0), 0.0)
        pnl = _as_float(entry.get("pnl", 0), 0.0)

        if (
            not isinstance(symbol, str)
            or not isinstance(exchange, str)
            or not isinstance(product, str)
        ):
            continue

        qty_f = float(quantity or 0.0)
        avg_price_f = float(avg_price or 0.0)
        pnl_f = float(pnl or 0.0)

        exch_u = exchange.strip().upper()
        symbol_u = symbol.strip().upper()
        symbol_key = _canon_symbol(symbol)
        key = (exch_u, symbol_key)
        holding_avg = holdings_avg.get(key)
        holding_qty_val = holdings_qty.get(key)

        if holding_avg is None or holding_qty_val is None:
            # Fallback: match by symbol only (any exchange) to be resilient
            # to NSE/BSE mismatches between positions and holdings.
            for (ex2, sym2), avg2 in holdings_avg.items():
                if sym2 != symbol_key:
                    continue
                holding_avg = avg2
                holding_qty_val = holdings_qty.get((ex2, sym2))
                break

        buy_qty = _as_float(entry.get("buy_quantity"))
        buy_avg = _as_float(entry.get("buy_price"))
        if product == "CNC" and holding_avg is not None and holding_avg > 0:
            # For delivery positions Zerodha often does not populate buy_price
            # on the positions payload for pure SELL days. Prefer holdings
            # average cost as the canonical entry price.
            buy_avg = holding_avg

        last_price = _as_float(entry.get("last_price"))
        close_price = _as_float(entry.get("close_price"))
        quote = ltp_map.get((exch_u, symbol_u), {})
        if last_price is None:
            qp = quote.get("last_price")
            last_price = float(qp) if qp is not None else None
        if close_price is None:
            qp = quote.get("prev_close")
            close_price = float(qp) if qp is not None else None

        snap = PositionSnapshot(
            broker_name=broker_name,
            as_of_date=as_of,
            captured_at=now,
            symbol=symbol_u,
            exchange=exch_u,
            product=product,
            qty=qty_f,
            avg_price=avg_price_f,
            pnl=pnl_f,
            last_price=last_price,
            close_price=close_price,
            value=_as_float(entry.get("value")),
            m2m=_as_float(entry.get("m2m")),
            unrealised=_as_float(entry.get("unrealised")),
            realised=_as_float(entry.get("realised")),
            buy_qty=buy_qty,
            buy_avg_price=buy_avg,
            sell_qty=_as_float(entry.get("sell_quantity")),
            sell_avg_price=_as_float(entry.get("sell_price")),
            day_buy_qty=_as_float(entry.get("day_buy_quantity")),
            day_buy_avg_price=_as_float(entry.get("day_buy_price")),
            day_sell_qty=_as_float(entry.get("day_sell_quantity")),
            day_sell_avg_price=_as_float(entry.get("day_sell_price")),
            holding_qty=holding_qty_val,
        )
        db.add(snap)
        updated += 1

    db.commit()

    return updated


def sync_positions_from_angelone(db: Session, client: AngelOneClient) -> int:
    """Fetch positions from AngelOne (SmartAPI) and cache them locally."""

    broker_name = "angelone"

    rows = client.list_positions()
    if not rows:
        db.query(Position).filter(Position.broker_name == broker_name).delete()
        db.commit()
        return 0

    db.query(Position).filter(Position.broker_name == broker_name).delete()

    updated = 0
    now = datetime.now(UTC)
    as_of = _as_of_date_ist(now)

    db.query(PositionSnapshot).filter(
        PositionSnapshot.broker_name == broker_name,
        PositionSnapshot.as_of_date == as_of,
    ).delete()

    for entry in rows:
        if not isinstance(entry, dict):
            continue

        sym_raw = (
            entry.get("tradingsymbol") or entry.get("symbol") or entry.get("symbolname")
        )
        exch_raw = entry.get("exchange") or "NSE"
        product_raw = (
            entry.get("producttype") or entry.get("product") or entry.get("productType")
        )

        if (
            not isinstance(sym_raw, str)
            or not isinstance(exch_raw, str)
            or not isinstance(product_raw, str)
        ):
            continue

        broker_symbol_u = sym_raw.strip().upper()
        exch_u = exch_raw.strip().upper()
        product = product_raw.strip().upper()

        listing = resolve_listing_for_broker_symbol(
            db,
            broker_name=broker_name,
            exchange=exch_u,
            broker_symbol=broker_symbol_u,
        )
        symbol_u = (
            listing.symbol.strip().upper() if listing is not None else broker_symbol_u
        )

        qty_f = float(
            _as_float(
                entry.get("netqty") or entry.get("netQty") or entry.get("qty"),
                0.0,
            )
            or 0.0
        )
        avg_price_f = float(
            _as_float(
                entry.get("avgnetprice")
                or entry.get("avgNetPrice")
                or entry.get("averageprice")
                or entry.get("avg_price"),
                0.0,
            )
            or 0.0
        )
        pnl_f = float(
            _as_float(
                entry.get("pnl") or entry.get("pnlvalue") or entry.get("pnlValue"),
                0.0,
            )
            or 0.0
        )

        last_price = _as_float(
            entry.get("ltp") or entry.get("last_price") or entry.get("lastPrice")
        )
        close_price = _as_float(
            entry.get("close") or entry.get("close_price") or entry.get("closePrice")
        )

        position = Position(
            broker_name=broker_name,
            symbol=symbol_u,
            exchange=exch_u,
            product=product,
            qty=qty_f,
            avg_price=avg_price_f,
            pnl=pnl_f,
            last_updated=now,
        )
        db.add(position)

        snap = PositionSnapshot(
            broker_name=broker_name,
            as_of_date=as_of,
            captured_at=now,
            symbol=symbol_u,
            exchange=exch_u,
            product=product,
            qty=qty_f,
            avg_price=avg_price_f,
            pnl=pnl_f,
            last_price=last_price,
            close_price=close_price,
            value=_as_float(entry.get("value")),
            m2m=_as_float(entry.get("m2m")),
            unrealised=_as_float(entry.get("unrealised")),
            realised=_as_float(entry.get("realised")),
            buy_qty=_as_float(entry.get("buyqty") or entry.get("buyQty")),
            buy_avg_price=_as_float(
                entry.get("buyavgprice") or entry.get("buyAvgPrice")
            ),
            sell_qty=_as_float(entry.get("sellqty") or entry.get("sellQty")),
            sell_avg_price=_as_float(
                entry.get("sellavgprice") or entry.get("sellAvgPrice")
            ),
            day_buy_qty=_as_float(entry.get("daybuyqty") or entry.get("dayBuyQty")),
            day_buy_avg_price=_as_float(
                entry.get("daybuyavgprice") or entry.get("dayBuyAvgPrice")
            ),
            day_sell_qty=_as_float(entry.get("daysellqty") or entry.get("daySellQty")),
            day_sell_avg_price=_as_float(
                entry.get("daysellavgprice") or entry.get("daySellAvgPrice")
            ),
            holding_qty=None,
        )
        db.add(snap)
        updated += 1

    db.commit()
    return updated


__all__ = ["sync_positions_from_zerodha", "sync_positions_from_angelone"]
