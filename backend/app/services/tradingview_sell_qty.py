from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    resolved_exchange: str | None = None
    resolved_symbol: str | None = None
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


def _get_str(d: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _holdings_total_qty(row: dict[str, Any]) -> float:
    # Zerodha holdings provide:
    # - quantity (T+1 settled)
    # - t1_quantity (unsettled)
    # Total sellable qty for CNC exits is typically quantity + t1_quantity.
    q = _as_float(row.get("quantity") or row.get("qty") or row.get("netqty")) or 0.0
    t1 = (
        _as_float(
            row.get("t1_quantity")
            or row.get("t1_qty")
            or row.get("t1Quantity")
            or row.get("t1Qty")
        )
        or 0.0
    )
    return float(q + t1)


def _position_net_qty(row: dict[str, Any]) -> float | None:
    return _as_float(
        row.get("quantity")
        or row.get("net_quantity")
        or row.get("netQuantity")
        or row.get("netqty")
        or row.get("netQty")
        or row.get("qty")
    )


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
    holdings_exch: str | None = None
    try:
        raw_holdings = client.list_holdings()
        for h in raw_holdings:
            if not isinstance(h, dict):
                continue
            hs = _get_str(h, "tradingsymbol", "symbol", "symbolname")
            he = _get_str(h, "exchange", "exch") or exch_u
            if not isinstance(hs, str) or not isinstance(he, str):
                continue
            if _canon(he) != exch_u or _canon(hs) != sym_u:
                continue
            holdings_qty = _holdings_total_qty(h)
            holdings_exch = _canon(he) or exch_u
            break
    except Exception:
        holdings_qty = 0.0

    # Fallback: symbol matches but exchange differs (or broker omits exchange).
    # This helps when TradingView alerts are configured for NSE/BSE differently
    # from the broker holdings record.
    if holdings_qty <= 0:
        try:
            raw_holdings = client.list_holdings()
            by_exch: dict[str, float] = {}
            for h in raw_holdings:
                if not isinstance(h, dict):
                    continue
                hs = _get_str(h, "tradingsymbol", "symbol", "symbolname")
                if not isinstance(hs, str) or _canon(hs) != sym_u:
                    continue
                he = _get_str(h, "exchange", "exch")
                he_u = _canon(str(he) if he is not None else "") or "UNKNOWN"
                q = _holdings_total_qty(h)
                if q > 0:
                    by_exch[he_u] = max(by_exch.get(he_u, 0.0), float(q))

            positive_exchs = [e for e, q in by_exch.items() if q > 0]
            if len(positive_exchs) == 1:
                holdings_exch = positive_exchs[0]
                holdings_qty = float(by_exch[holdings_exch] or 0.0)
        except Exception:
            pass

    if holdings_qty > 0:
        note = "Resolved from live broker holdings."
        if holdings_exch and holdings_exch not in {"UNKNOWN", exch_u}:
            note = f"{note} Matched holdings on {holdings_exch} while alert was {exch_u}."
        return TradingViewSellQtyResolution(
            qty=float(holdings_qty),
            source="holdings",
            resolved_product="CNC",
            resolved_exchange=holdings_exch if holdings_exch and holdings_exch != "UNKNOWN" else exch_u,
            resolved_symbol=sym_u,
            is_exit=True,
            checked_live=True,
            reject=False,
            note=note,
        )

    # No holdings -> check positions.
    positions_qty_by_product: dict[str, float] = {}
    positions_exch: str | None = None
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
            ps = _get_str(row, "tradingsymbol", "symbol", "symbolname")
            pe = _get_str(row, "exchange", "exch") or exch_u
            if not isinstance(ps, str) or not isinstance(pe, str):
                continue
            if _canon(pe) != exch_u or _canon(ps) != sym_u:
                continue
            positions_exch = _canon(pe) or exch_u

            prod = row.get("product") or row.get("producttype") or row.get("productType")
            prod_u = _canon(str(prod) if prod is not None else "")
            if not prod_u:
                continue

            q = _position_net_qty(row)
            if q is None:
                continue
            positions_qty_by_product[prod_u] = float(q or 0.0)
    except Exception:
        positions_qty_by_product = {}

    # Fallback: symbol matches but exchange differs.
    if not any(float(v or 0.0) > 0 for v in positions_qty_by_product.values()):
        try:
            raw_positions = client.list_positions()
            if isinstance(raw_positions, dict):
                net = raw_positions.get("net")
                rows = net if isinstance(net, list) else []
            elif isinstance(raw_positions, list):
                rows = raw_positions
            else:
                rows = []

            by_exch: dict[str, dict[str, float]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ps = _get_str(row, "tradingsymbol", "symbol", "symbolname")
                if not isinstance(ps, str) or _canon(ps) != sym_u:
                    continue
                pe = _get_str(row, "exchange", "exch")
                pe_u = _canon(str(pe) if pe is not None else "") or "UNKNOWN"
                prod = row.get("product") or row.get("producttype") or row.get("productType")
                prod_u = _canon(str(prod) if prod is not None else "")
                if not prod_u:
                    continue
                q = _position_net_qty(row)
                if q is None:
                    continue
                qf = float(q or 0.0)
                if qf <= 0:
                    continue
                by_exch.setdefault(pe_u, {})
                by_exch[pe_u][prod_u] = max(by_exch[pe_u].get(prod_u, 0.0), qf)

            positive_exchs = [e for e, prods in by_exch.items() if any(v > 0 for v in prods.values())]
            if len(positive_exchs) == 1:
                positions_exch = positive_exchs[0]
                positions_qty_by_product = by_exch[positions_exch]
        except Exception:
            pass

    # Preferred: desired product first, then fall back to any other positive qty.
    candidates = [product_u]
    for k in sorted(positions_qty_by_product.keys()):
        if k not in candidates:
            candidates.append(k)

    for prod in candidates:
        q = float(positions_qty_by_product.get(prod, 0.0) or 0.0)
        if q > 0:
            note = "Resolved from live broker positions."
            if positions_exch and positions_exch not in {"UNKNOWN", exch_u}:
                note = f"{note} Matched positions on {positions_exch} while alert was {exch_u}."
            return TradingViewSellQtyResolution(
                qty=q,
                source="positions",
                resolved_product=prod,
                resolved_exchange=positions_exch
                if positions_exch and positions_exch != "UNKNOWN"
                else exch_u,
                resolved_symbol=sym_u,
                is_exit=True,
                checked_live=True,
                reject=False,
                note=note,
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
