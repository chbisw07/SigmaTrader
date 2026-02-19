from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Callable

from app.core.config import Settings


class SafeSummaryError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _salt(settings: Settings) -> str:
    return str(settings.hash_salt or settings.crypto_key or "st-hash-salt")


def hash_identifier(settings: Settings, raw_id: str) -> str:
    s = (raw_id or "").strip()
    if not s:
        return ""
    h = hashlib.sha256((f"{_salt(settings)}:{s}").encode("utf-8")).hexdigest()
    return h


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_holdings(payload: Any) -> list[dict[str, Any]]:
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
        ltp = _as_float(r.get("last_price")) or _as_float(r.get("ltp")) or 0.0
        invested = float(qty) * float(avg)
        current = float(qty) * float(ltp)
        pnl = _as_float(r.get("pnl"))
        if pnl is None:
            pnl = current - invested
        pnl_pct = (float(pnl) / invested * 100.0) if invested > 0 else None
        out.append(
            {
                "symbol": sym,
                "qty": float(qty),
                "avg_price": float(avg) if avg else None,
                "ltp": float(ltp) if ltp else None,
                "invested": invested,
                "current": current,
                "pnl_abs": float(pnl),
                "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
            }
        )
    return out


def holdings_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    rows = _normalize_holdings(raw_payload)
    invested = sum(float(r.get("invested") or 0.0) for r in rows)
    current = sum(float(r.get("current") or 0.0) for r in rows)
    pnl_abs = current - invested
    pnl_pct = (pnl_abs / invested * 100.0) if invested > 0 else None

    rows_sorted = sorted(rows, key=lambda r: float(r.get("current") or 0.0), reverse=True)
    top = []
    for r in rows_sorted[:15]:
        weight = (float(r.get("current") or 0.0) / current * 100.0) if current > 0 else None
        top.append(
            {
                "symbol": r["symbol"],
                "qty": int(r["qty"]) if float(r["qty"]).is_integer() else float(r["qty"]),
                "avg_price": r.get("avg_price"),
                "ltp": r.get("ltp"),
                "pnl_abs": r.get("pnl_abs"),
                "pnl_pct": r.get("pnl_pct"),
                "weight_pct": float(weight) if weight is not None else None,
            }
        )

    return {
        "schema": "holdings_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "totals": {
            "invested": invested,
            "current": current,
            "pnl_abs": pnl_abs,
            "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
            "count": len(rows),
        },
        "top": top,
    }


def _normalize_positions(payload: Any) -> list[dict[str, Any]]:
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
                "pnl_abs": float(pnl) if pnl is not None else None,
                "notional": float(notional),
            }
        )
    return out


def positions_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    rows = _normalize_positions(raw_payload)
    exp: dict[str, float] = {}
    for r in rows:
        prod = str(r.get("product") or "CNC").upper()
        exp[prod] = exp.get(prod, 0.0) + float(r.get("notional") or 0.0)

    def _risk_score(r: dict[str, Any]) -> float:
        pnl = r.get("pnl_abs")
        return abs(float(pnl)) if pnl is not None else 0.0

    top_risk = sorted(rows, key=_risk_score, reverse=True)[:15]
    top = []
    for r in top_risk:
        pnl_abs = r.get("pnl_abs")
        invested = abs(float(r.get("qty") or 0.0)) * float(r.get("avg_price") or 0.0)
        pnl_pct = (float(pnl_abs) / invested * 100.0) if invested > 0 and pnl_abs is not None else None
        top.append(
            {
                "symbol": r["symbol"],
                "product": r.get("product"),
                "qty": int(r["qty"]) if float(r["qty"]).is_integer() else float(r["qty"]),
                "avg_price": r.get("avg_price"),
                "ltp": r.get("ltp"),
                "pnl_abs": pnl_abs,
                "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
            }
        )

    return {
        "schema": "positions_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "exposure_by_product": exp,
        "top_risk_positions": top,
        "count": len(rows),
    }


def margins_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    # Best-effort: different MCP servers shape margins differently.
    available = _as_float(payload.get("available")) or _as_float(payload.get("cash")) or 0.0
    utilized = _as_float(payload.get("utilised")) or _as_float(payload.get("utilized")) or 0.0
    if utilized == 0.0 and "equity" in payload and isinstance(payload.get("equity"), (int, float)):
        available = float(payload.get("equity") or 0.0)
    total = available + utilized
    utilization_pct = (utilized / total * 100.0) if total > 0 else None
    return {
        "schema": "margins_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "available": available,
        "utilized": utilized,
        "utilization_pct": float(utilization_pct) if utilization_pct is not None else None,
    }


def orders_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:
    rows = raw_payload if isinstance(raw_payload, list) else []
    if not isinstance(rows, list):
        rows = []
    counts: dict[str, int] = {}
    recent: list[dict[str, Any]] = []
    for o in rows[-25:]:
        if not isinstance(o, dict):
            continue
        status = str(o.get("status") or "UNKNOWN").strip().upper()
        counts[status] = counts.get(status, 0) + 1
    for o in rows[-10:]:
        if not isinstance(o, dict):
            continue
        raw_id = str(o.get("order_id") or o.get("exchange_order_id") or "")
        recent.append(
            {
                "status": str(o.get("status") or "UNKNOWN").strip().upper(),
                "symbol": str(o.get("tradingsymbol") or o.get("symbol") or "").strip().upper(),
                "side": str(o.get("transaction_type") or o.get("side") or "").strip().upper(),
                "qty": int(float(o.get("quantity") or 0.0)),
                "price_type": str(o.get("order_type") or "MARKET").strip().upper(),
                "ts": str(o.get("order_timestamp") or o.get("timestamp") or ""),
                "id_hash": hash_identifier(settings, raw_id)[:16],
            }
        )
    return {
        "schema": "orders_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "counts_by_status": counts,
        "recent": recent,
        "count": len(rows),
    }


def propose_trade_plan_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    if not isinstance(raw_payload, dict):
        raise SafeSummaryError("invalid internal tool payload")
    plan = raw_payload.get("plan") if isinstance(raw_payload.get("plan"), dict) else {}
    return {
        "schema": "trade_plan_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "plan": {
            "plan_id": str(plan.get("plan_id") or raw_payload.get("plan_id") or ""),
            "intent": plan.get("intent") if isinstance(plan.get("intent"), dict) else {},
            "risk_model": plan.get("risk_model") if isinstance(plan.get("risk_model"), dict) else {},
        },
        "plan_hash": str(raw_payload.get("plan_hash") or ""),
    }


def execute_trade_plan_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise SafeSummaryError("invalid internal tool payload")
    executed = bool(raw_payload.get("executed"))
    veto = bool(raw_payload.get("veto"))
    reason = str(raw_payload.get("reason") or "") or None
    ex = raw_payload.get("execution") if isinstance(raw_payload.get("execution"), dict) else {}
    orders = ex.get("orders") if isinstance(ex.get("orders"), list) else []
    order_hashes: list[str] = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        raw_id = str(o.get("broker_order_id") or "")
        if raw_id:
            order_hashes.append(hash_identifier(settings, raw_id)[:16])
    return {
        "schema": "execution_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "executed": executed,
        "veto": veto,
        "reason": reason,
        "orders": order_hashes,
    }


Summarizer = Callable[[Settings, Any], dict[str, Any]]


_REGISTRY: dict[str, Summarizer] = {
    "get_holdings": holdings_safe_summary,
    "get_positions": positions_safe_summary,
    "get_margins": margins_safe_summary,
    "get_orders": orders_safe_summary,
    # Internal tools
    "propose_trade_plan": propose_trade_plan_safe_summary,
    "execute_trade_plan": execute_trade_plan_safe_summary,
}


def tool_has_safe_summary(tool_name: str) -> bool:
    return (tool_name or "").strip() in _REGISTRY


def summarize_tool_for_llm(settings: Settings, *, tool_name: str, operator_payload: Any) -> dict[str, Any]:
    fn = _REGISTRY.get((tool_name or "").strip())
    if fn is None:
        raise SafeSummaryError(f"no safe summarizer registered for tool: {tool_name}")
    out = fn(settings, operator_payload)
    # Ensure JSON-serializable.
    json.dumps(out, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
    return out


__all__ = [
    "SafeSummaryError",
    "hash_identifier",
    "summarize_tool_for_llm",
    "tool_has_safe_summary",
]
