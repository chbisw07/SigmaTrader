from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import Position
from app.schemas.managed_risk import DistanceSpec, RiskSpec
from app.schemas.webhook import TradingViewWebhookPayload


def _canon(s: object) -> str:
    return str(s or "").strip().upper()


def _parse_float(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s.replace(",", ""))
        except Exception:
            return None
    return None


def _parse_boolish(v: object) -> bool:
    if isinstance(v, bool):
        return bool(v)
    if v is None:
        return False
    s = str(v).strip().lower()
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return False


def _extract_position_rows(raw: object) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        # Zerodha returns {"net": [...], "day": [...]}
        for key in ("net", "positions", "data", "day"):
            rows = raw.get(key)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
    return []


def _position_qty(row: dict[str, Any]) -> float | None:
    for k in (
        "quantity",
        "net_quantity",
        "netQuantity",
        "netqty",
        "netQty",
        "qty",
    ):
        if row.get(k) is not None:
            return _parse_float(row.get(k))
    return None


def extract_signal_side(payload: TradingViewWebhookPayload) -> str | None:
    try:
        v = (payload.hints or {}).get("signal_side")
    except Exception:
        v = None
    s = _canon(v)
    return s or None


def is_exit_signal(signal_side: str | None) -> bool:
    s = _canon(signal_side)
    return bool(s.startswith(("EXIT_", "CLOSE_")))


def resolve_action_from_signal_side(
    signal_side: str | None,
    *,
    fallback: str,
) -> str:
    """Resolve BUY/SELL action, using semantic side when available."""

    s = _canon(signal_side)
    if s.startswith("ENTRY_"):
        if "SHORT" in s:
            return "SELL"
        if "LONG" in s:
            return "BUY"
    if s.startswith(("EXIT_", "CLOSE_")):
        if "SHORT" in s:
            return "BUY"
        if "LONG" in s:
            return "SELL"
    fb = _canon(fallback)
    return fb if fb in {"BUY", "SELL"} else fallback


def resolve_product(
    payload: TradingViewWebhookPayload,
    *,
    default_product: str,
) -> str:
    desired = _canon(getattr(payload.trade_details, "product", None))
    if desired in {"MIS", "CNC"}:
        return desired
    fallback = _canon(default_product) or "CNC"
    return fallback if fallback in {"MIS", "CNC"} else "CNC"


def resolve_qty_from_payload(payload: TradingViewWebhookPayload) -> float | None:
    q = _parse_float(getattr(payload.trade_details, "quantity", None))
    if q is not None and float(q) > 0:
        return float(q)

    # Strategy v6 fallback: use position_size when qty is missing.
    try:
        pos_size = _parse_float((payload.hints or {}).get("position_size"))
    except Exception:
        pos_size = None
    if pos_size is not None and float(pos_size) > 0:
        return float(pos_size)

    return None


def resolve_exit_qty_from_cached_positions(
    db: Session,
    *,
    broker_name: str,
    exchange: str,
    symbol: str,
    product: str,
    signal_side: str | None,
) -> float | None:
    """Resolve exit qty from cached positions (never from holdings)."""

    broker = (broker_name or "zerodha").strip().lower() or "zerodha"
    exch_u = _canon(exchange or "NSE") or "NSE"
    sym_u = _canon(symbol)
    prod_u = _canon(product or "MIS") or "MIS"

    pos = (
        db.query(Position)
        .filter(
            Position.broker_name == broker,
            Position.exchange == exch_u,
            Position.symbol == sym_u,
            Position.product == prod_u,
        )
        .one_or_none()
    )
    if pos is None:
        return None

    try:
        qty = float(getattr(pos, "qty", 0.0) or 0.0)
    except Exception:
        return None
    if qty == 0:
        return None

    sside = _canon(signal_side)
    if "LONG" in sside and qty <= 0:
        return None
    if "SHORT" in sside and qty >= 0:
        return None
    return float(abs(qty))


def resolve_exit_qty_from_live_positions(
    db: Session,
    settings: Any,
    *,
    user_id: int,
    broker_name: str,
    exchange: str,
    symbol: str,
    product: str,
    signal_side: str | None,
) -> float | None:
    """Resolve exit qty by querying the broker positions endpoint (never holdings)."""

    broker = (broker_name or "zerodha").strip().lower() or "zerodha"
    exch_u = _canon(exchange or "NSE") or "NSE"
    sym_u = _canon(symbol)
    prod_u = _canon(product or "MIS") or "MIS"

    client = None
    try:
        from app.api.orders import _get_broker_client

        client = _get_broker_client(db, settings, broker, user_id=int(user_id))
    except Exception:
        client = None
    if client is None:
        return None

    try:
        raw_positions = client.list_positions()
    except Exception:
        return None

    rows = _extract_position_rows(raw_positions)
    if not rows:
        return None

    best: float | None = None
    for row in rows:
        rs = row.get("tradingsymbol") or row.get("symbol") or row.get("symbolname")
        re = row.get("exchange") or row.get("exch") or row.get("Exchange") or exch_u
        rp = row.get("product") or row.get("prod") or row.get("Product")
        if not isinstance(rs, str) or not isinstance(re, str) or not isinstance(rp, str):
            continue
        if _canon(re) != exch_u or _canon(rs) != sym_u or _canon(rp) != prod_u:
            continue
        q = _position_qty(row)
        if q is None or float(q) == 0:
            continue
        # Keep the largest absolute qty if multiple rows match.
        cand = float(q)
        if best is None or abs(cand) > abs(best):
            best = cand

    if best is None or float(best) == 0:
        return None

    sside = _canon(signal_side)
    if "LONG" in sside and float(best) <= 0:
        return None
    if "SHORT" in sside and float(best) >= 0:
        return None
    return float(abs(best))


def _pct_distance(ref_price: float, target_price: float) -> float | None:
    if ref_price <= 0:
        return None
    dist = abs(float(ref_price) - float(target_price))
    if dist <= 0:
        return None
    return float(dist) * 100.0 / float(ref_price)


@dataclass(frozen=True)
class TradingViewRiskFromHints:
    risk_spec_json: str | None
    details: dict[str, Any]


def build_risk_spec_from_hints(
    payload: TradingViewWebhookPayload,
    *,
    ref_price: float | None,
) -> TradingViewRiskFromHints:
    """Build a SigmaTrader-managed RiskSpec from TradingView v6 hints."""

    details: dict[str, Any] = {}
    if ref_price is None or float(ref_price) <= 0:
        return TradingViewRiskFromHints(risk_spec_json=None, details=details)

    hints = payload.hints or {}
    stop_price = _parse_float(hints.get("stop_price"))
    stop_type = str(hints.get("stop_type") or "").strip().upper() or None
    tp_enabled = _parse_boolish(hints.get("tp_enabled"))
    take_profit = _parse_float(hints.get("take_profit"))
    trail_enabled = _parse_boolish(hints.get("trail_enabled"))
    trail_dist = _parse_float(hints.get("trail_dist"))

    details.update(
        {
            "stop_type": stop_type,
            "stop_price": stop_price,
            "tp_enabled": bool(tp_enabled),
            "take_profit": take_profit,
            "trail_enabled": bool(trail_enabled),
            "trail_dist": trail_dist,
        }
    )

    stop_abs = None
    if stop_price is not None and stop_price > 0:
        stop_abs = abs(float(ref_price) - float(stop_price))

    tp_abs = None
    if tp_enabled and take_profit is not None and take_profit > 0:
        tp_abs = abs(float(take_profit) - float(ref_price))

    trail_abs = None
    if trail_enabled and trail_dist is not None and trail_dist > 0:
        trail_abs = float(trail_dist)

    if stop_abs is None and tp_abs is None and trail_abs is None:
        return TradingViewRiskFromHints(risk_spec_json=None, details=details)

    spec = RiskSpec(
        stop_loss=DistanceSpec(
            enabled=bool(stop_abs is not None and stop_abs > 0),
            mode="ABS",
            value=float(stop_abs or 0.0),
        ),
        take_profit=DistanceSpec(
            enabled=bool(tp_abs is not None and tp_abs > 0),
            mode="ABS",
            value=float(tp_abs or 0.0),
        ),
        trailing_stop=DistanceSpec(
            enabled=bool(trail_abs is not None and trail_abs > 0 and stop_abs is not None and stop_abs > 0),
            mode="ABS",
            value=float(trail_abs or 0.0),
        ),
        trailing_activation=DistanceSpec(enabled=False, mode="PCT", value=0.0),
        exit_order_type="MARKET",
    )
    return TradingViewRiskFromHints(risk_spec_json=spec.to_json(), details=details)


__all__ = [
    "extract_signal_side",
    "is_exit_signal",
    "resolve_action_from_signal_side",
    "resolve_product",
    "resolve_qty_from_payload",
    "resolve_exit_qty_from_cached_positions",
    "resolve_exit_qty_from_live_positions",
    "build_risk_spec_from_hints",
    "TradingViewRiskFromHints",
]
