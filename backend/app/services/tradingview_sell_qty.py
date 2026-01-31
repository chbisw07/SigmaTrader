from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Position, User


@dataclass(frozen=True)
class TradingViewSellQtyResolution:
    """Best-effort resolution of qty for TradingView SELL alerts.

    This is intentionally conservative:
    - Only returns `reject=True` when we successfully checked live broker state
      and found no sellable quantity (caller decides whether to block, queue,
      or attempt execution).
    - When broker state can't be fetched (not connected / temporary error),
      we fall back to payload qty (legacy behavior).
    """

    qty: float
    source: str  # holdings|positions|payload
    resolved_product: str | None = None
    is_exit: bool = False
    checked_live: bool = False
    reject: bool = False
    note: str | None = None


def _as_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _canon(s: str) -> str:
    return (s or "").strip().upper()


def _lookup_cached_position_qty(
    db: Session,
    *,
    broker_name: str,
    exchange: str,
    symbol: str,
    product: str,
) -> float | None:
    pos = (
        db.query(Position)
        .filter(
            Position.broker_name == (broker_name or "zerodha").strip().lower(),
            Position.exchange == _canon(exchange or "NSE"),
            Position.symbol == _canon(symbol),
            Position.product == _canon(product),
        )
        .one_or_none()
    )
    if pos is None:
        return None
    try:
        return float(getattr(pos, "qty", 0.0) or 0.0)
    except Exception:
        return None


def resolve_tradingview_sell_qty(
    db: Session,
    settings: Settings,
    *,
    user: User,
    broker_name: str,
    exchange: str,
    symbol: str,
    desired_product: str,
    payload_qty: float,
) -> TradingViewSellQtyResolution:
    """Resolve a safe SELL qty for TradingView-originated orders.

    Intended behavior (requested):
    - Prefer delivery holdings qty (when > 0) as the target qty for SELL.
    - If holdings qty is 0, check positions (intraday/delivery) and use that qty.
    - If neither exists, return reject=True so the caller can decide what to do
      (recommended: create a WAITING order for user review).

    Practical constraint:
    - Broker state fetch can fail (not connected, rate limits, network).
      In that case we fall back to the TradingView payload qty to avoid
      breaking existing flows/tests.
    """

    broker = (broker_name or "zerodha").strip().lower()
    exch_u = _canon(exchange or "NSE") or "NSE"
    sym_u = _canon(symbol)
    product_u = _canon(desired_product or "CNC") or "CNC"

    # 1) Cheap best-effort: if we already have a cached position (from a recent
    # /positions/sync), use it as a hint. This keeps SELL exits working even
    # when the broker API is temporarily unavailable.
    cached_qty = _lookup_cached_position_qty(
        db,
        broker_name=broker,
        exchange=exch_u,
        symbol=sym_u,
        product=product_u,
    )
    if cached_qty is not None and cached_qty > 0:
        return TradingViewSellQtyResolution(
            qty=float(cached_qty),
            source="positions",
            resolved_product=product_u,
            is_exit=True,
            checked_live=False,
            reject=False,
            note="Resolved from cached positions table.",
        )

    # 2) Live broker fetch (authoritative when available).
    client: Any | None = None
    try:
        from app.api.orders import _get_broker_client

        client = _get_broker_client(db, settings, broker, user_id=user.id)
    except Exception:
        client = None

    if client is None:
        # Fall back to legacy behavior (payload qty). Do not "reject" because
        # we could not confirm absence of holdings/positions.
        return TradingViewSellQtyResolution(
            qty=float(payload_qty or 0.0),
            source="payload",
            resolved_product=product_u,
            is_exit=False,
            checked_live=False,
            reject=False,
            note="Broker client unavailable; using TradingView payload qty.",
        )

    holdings_qty: float = 0.0
    try:
        raw_holdings = client.list_holdings()
        for h in raw_holdings:
            if not isinstance(h, dict):
                continue
            hs = h.get("tradingsymbol") or h.get("symbol") or h.get("symbolname")
            he = h.get("exchange") or exch_u
            if not isinstance(hs, str) or not isinstance(he, str):
                continue
            if _canon(he) != exch_u or _canon(hs) != sym_u:
                continue
            q = _as_float(h.get("quantity") or h.get("qty") or h.get("netqty"))
            if q is not None:
                holdings_qty = float(q or 0.0)
                break
    except Exception:
        holdings_qty = 0.0

    if holdings_qty > 0:
        return TradingViewSellQtyResolution(
            qty=float(holdings_qty),
            source="holdings",
            resolved_product="CNC",
            is_exit=True,
            checked_live=True,
            reject=False,
            note="Resolved from live broker holdings.",
        )

    # No holdings -> check positions.
    positions_qty_by_product: dict[str, float] = {}
    try:
        raw_positions = client.list_positions()
        if isinstance(raw_positions, dict):
            # Zerodha shape: {"net": [ ... ] }
            net = raw_positions.get("net")
            rows = net if isinstance(net, list) else []
        elif isinstance(raw_positions, list):
            # AngelOne shape: [ ... ]
            rows = raw_positions
        else:
            rows = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            ps = row.get("tradingsymbol") or row.get("symbol") or row.get("symbolname")
            pe = row.get("exchange") or exch_u
            if not isinstance(ps, str) or not isinstance(pe, str):
                continue
            if _canon(pe) != exch_u or _canon(ps) != sym_u:
                continue

            prod = row.get("product") or row.get("producttype") or row.get("productType")
            prod_u = _canon(str(prod) if prod is not None else "")
            if not prod_u:
                continue

            q = _as_float(
                row.get("quantity")
                or row.get("netqty")
                or row.get("netQty")
                or row.get("qty")
            )
            if q is None:
                continue
            positions_qty_by_product[prod_u] = float(q or 0.0)
    except Exception:
        positions_qty_by_product = {}

    # Preferred: desired product first, then fall back to any other positive qty.
    candidates = [product_u]
    for k in sorted(positions_qty_by_product.keys()):
        if k not in candidates:
            candidates.append(k)

    for prod in candidates:
        q = float(positions_qty_by_product.get(prod, 0.0) or 0.0)
        if q > 0:
            return TradingViewSellQtyResolution(
                qty=q,
                source="positions",
                resolved_product=prod,
                is_exit=True,
                checked_live=True,
                reject=False,
                note="Resolved from live broker positions.",
            )

    # Live check completed and we found no sellable quantity.
    return TradingViewSellQtyResolution(
        qty=0.0,
        source="payload",
        resolved_product=product_u,
        is_exit=False,
        checked_live=True,
        reject=True,
        note="No holdings or long positions found for symbol; rejecting TV SELL.",
    )


__all__ = ["TradingViewSellQtyResolution", "resolve_tradingview_sell_qty"]
