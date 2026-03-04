from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple

from app.schemas.ai_settings import AiSettings


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _holdings_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("holdings"), list):
        rows = [r for r in payload.get("holdings") if isinstance(r, dict)]
    out: list[dict[str, Any]] = []
    for r in rows:
        sym = str(r.get("tradingsymbol") or r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        qty = _as_float(r.get("quantity")) or _as_float(r.get("qty")) or 0.0
        avg = _as_float(r.get("average_price")) or _as_float(r.get("avg_price")) or 0.0
        ltp = _as_float(r.get("last_price")) or _as_float(r.get("ltp"))
        pnl = _as_float(r.get("pnl")) or _as_float(r.get("pnl_unrealised")) or _as_float(r.get("pnl_unrealized"))
        notional = abs(float(qty)) * float(ltp or avg)
        out.append(
            {
                "symbol": sym,
                "product": str(r.get("product") or "CNC").strip().upper(),
                "qty": float(qty),
                "avg_price": float(avg) if avg else None,
                "ltp": float(ltp) if ltp is not None else None,
                "pnl": float(pnl) if pnl is not None else None,
                "notional": float(notional),
            }
        )
    return out


def _positions_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("net"), list):
        rows = [r for r in payload.get("net") if isinstance(r, dict)]
    elif isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    out: list[dict[str, Any]] = []
    for r in rows:
        sym = str(r.get("tradingsymbol") or r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        qty = _as_float(r.get("quantity")) or _as_float(r.get("qty")) or 0.0
        if qty == 0:
            continue
        avg = _as_float(r.get("average_price")) or _as_float(r.get("avg_price")) or 0.0
        ltp = _as_float(r.get("last_price")) or _as_float(r.get("ltp"))
        pnl = _as_float(r.get("pnl")) or _as_float(r.get("pnl_unrealised")) or _as_float(r.get("pnl_unrealized"))
        notional = abs(float(qty)) * float(ltp or avg)
        out.append(
            {
                "symbol": sym,
                "product": str(r.get("product") or "CNC").strip().upper(),
                "qty": float(qty),
                "avg_price": float(avg) if avg else None,
                "ltp": float(ltp) if ltp is not None else None,
                "pnl": float(pnl) if pnl is not None else None,
                "notional": float(notional),
            }
        )
    return out


def _normalize_margins(payload: Any) -> dict[str, Any]:
    p = payload if isinstance(payload, dict) else {}
    if isinstance(p.get("data"), dict):
        p = p.get("data") or p
    available = _as_float(p.get("available")) or _as_float(p.get("cash")) or 0.0
    utilized = _as_float(p.get("utilised")) or _as_float(p.get("utilized")) or 0.0
    if utilized == 0.0 and "equity" in p and isinstance(p.get("equity"), (int, float)):
        available = float(p.get("equity") or 0.0)
    total = available + utilized
    utilization_pct = (utilized / total * 100.0) if total > 0 else None
    return {
        "available": float(available),
        "utilized": float(utilized),
        "utilization_pct": float(utilization_pct) if utilization_pct is not None else None,
    }


def portfolio_digest(
    *,
    tm_cfg: AiSettings,
    holdings_payload: Any,
    positions_payload: Any,
    margins_payload: Any,
    top_n: int = 5,
) -> dict[str, Any]:
    holdings = _holdings_rows(holdings_payload)
    positions = _positions_rows(positions_payload)
    margins = _normalize_margins(margins_payload)

    holdings_symbols = sorted({str(r.get("symbol") or "").strip().upper() for r in holdings if r.get("symbol")})
    positions_symbols = sorted({str(r.get("symbol") or "").strip().upper() for r in positions if r.get("symbol")})
    symbols_all = sorted({*holdings_symbols, *positions_symbols})

    exposure: dict[str, float] = {}
    for r in holdings + positions:
        prod = str(r.get("product") or "CNC").upper()
        exposure[prod] = exposure.get(prod, 0.0) + float(r.get("notional") or 0.0)

    def _risk_score(r: dict[str, Any]) -> float:
        pnl = r.get("pnl")
        notional = r.get("notional")
        return abs(float(pnl)) + abs(float(notional)) * 0.001 if pnl is not None and notional is not None else abs(float(notional or 0.0))

    top = sorted(holdings + positions, key=_risk_score, reverse=True)[: max(1, min(int(top_n), 25))]
    top_syms = [
        {
            "symbol": r.get("symbol"),
            "product": r.get("product"),
            "qty": r.get("qty"),
            "avg_price": r.get("avg_price"),
            "ltp": r.get("ltp"),
            "pnl": r.get("pnl"),
            "notional": r.get("notional"),
        }
        for r in top
    ]

    # Aggregate PnL if present.
    total_pnl = 0.0
    pnl_any = False
    for r in holdings + positions:
        if r.get("pnl") is None:
            continue
        pnl_any = True
        total_pnl += float(r.get("pnl") or 0.0)

    return {
        "schema": "portfolio_digest.v1",
        "as_of_ts": _now_iso(),
        "counts": {"holdings": len(holdings), "positions": len(positions)},
        # Full symbol list (no raw broker identifiers). This enables remote reasoning
        # over the whole portfolio without sending raw holdings/positions payloads.
        "symbols_all": symbols_all,
        "holdings_symbols": holdings_symbols,
        "positions_symbols": positions_symbols,
        "exposure_by_product": exposure,
        "top_symbols": top_syms,
        "margins": margins,
        "pnl_total": float(total_pnl) if pnl_any else None,
        "policy_flags": {
            "ai_execution_enabled": bool(tm_cfg.feature_flags.ai_execution_enabled),
            "execution_kill_switch": bool(tm_cfg.kill_switch.ai_execution_kill_switch),
            "hybrid_llm_enabled": bool(getattr(getattr(tm_cfg, "hybrid_llm", None), "enabled", False)),
        },
    }


def orders_digest(*, orders_payload: Any, last_n: int = 10) -> dict[str, Any]:
    rows = orders_payload if isinstance(orders_payload, list) else []
    last_n2 = max(1, min(int(last_n), 25))
    counts: dict[str, int] = {}
    for o in rows:
        if not isinstance(o, dict):
            continue
        status = str(o.get("status") or "UNKNOWN").strip().upper()
        counts[status] = counts.get(status, 0) + 1

    recent: list[dict[str, Any]] = []
    for o in rows[-last_n2:]:
        if not isinstance(o, dict):
            continue
        recent.append(
            {
                "status": str(o.get("status") or "UNKNOWN").strip().upper(),
                "symbol": str(o.get("tradingsymbol") or o.get("symbol") or "").strip().upper(),
                "side": str(o.get("transaction_type") or o.get("side") or "").strip().upper(),
                "qty": int(float(o.get("quantity") or o.get("qty") or 0.0)),
                "order_type": str(o.get("order_type") or "MARKET").strip().upper(),
                "ts": str(o.get("order_timestamp") or o.get("timestamp") or ""),
                # Intentionally keep raw id under a canonical key so the sanitizer can hash it.
                "order_id": str(o.get("order_id") or o.get("exchange_order_id") or ""),
            }
        )

    return {
        "schema": "orders_digest.v1",
        "as_of_ts": _now_iso(),
        "counts_by_status": counts,
        "recent": recent,
        "count": len([o for o in rows if isinstance(o, dict)]),
    }


def risk_digest(
    *,
    tm_cfg: AiSettings,
    margins_payload: Any,
    holdings_payload: Any,
    positions_payload: Any,
) -> dict[str, Any]:
    margins = _normalize_margins(margins_payload)
    holdings = _holdings_rows(holdings_payload)
    positions = _positions_rows(positions_payload)

    # Best-effort realized/unrealized bucket: sum of pnl fields if present.
    pnl_total = 0.0
    pnl_any = False
    for r in holdings + positions:
        if r.get("pnl") is None:
            continue
        pnl_any = True
        pnl_total += float(r.get("pnl") or 0.0)

    # Policy flags that matter for execution safety.
    hy = getattr(tm_cfg, "hybrid_llm", None)
    return {
        "schema": "risk_digest.v1",
        "as_of_ts": _now_iso(),
        "margins": margins,
        "pnl_total": float(pnl_total) if pnl_any else None,
        "policy_flags": {
            "ai_execution_enabled": bool(tm_cfg.feature_flags.ai_execution_enabled),
            "execution_kill_switch": bool(tm_cfg.kill_switch.ai_execution_kill_switch),
            "execution_disabled_until_ts": str(tm_cfg.kill_switch.execution_disabled_until_ts)
            if tm_cfg.kill_switch.execution_disabled_until_ts is not None
            else None,
            "kite_mcp_enabled": bool(tm_cfg.feature_flags.kite_mcp_enabled),
            "kite_mcp_last_status": str(getattr(tm_cfg.kite_mcp, "last_status", "") or ""),
            "hybrid_llm_enabled": bool(getattr(hy, "enabled", False)),
            "remote_market_data_tools_enabled": bool(getattr(hy, "allow_remote_market_data_tools", False)),
            "remote_account_digests_enabled": bool(getattr(hy, "allow_remote_account_digests", False)),
        },
    }


__all__ = ["orders_digest", "portfolio_digest", "risk_digest"]
