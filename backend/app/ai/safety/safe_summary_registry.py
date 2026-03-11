from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlparse
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
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = [r for r in payload.get("data") if isinstance(r, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        inner = payload.get("data") or {}
        if isinstance(inner, dict) and isinstance(inner.get("holdings"), list):
            rows = [r for r in inner.get("holdings") if isinstance(r, dict)]
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
    symbols_all = sorted({str(r.get("symbol") or "").strip().upper() for r in rows if str(r.get("symbol") or "").strip()})
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
        # Symbols list helps the model avoid false negatives when a holding is not in "top".
        # This is still Tier-2 portfolio telemetry (no identity/PII).
        "symbols": symbols_all,
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
    elif isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        inner = payload.get("data") or {}
        if isinstance(inner, dict) and isinstance(inner.get("net"), list):
            rows = [r for r in inner.get("net") if isinstance(r, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = [r for r in payload.get("data") if isinstance(r, dict)]
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
    symbols_all = sorted({str(r.get("symbol") or "").strip().upper() for r in rows if str(r.get("symbol") or "").strip()})
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
        "symbols": symbols_all,
        "exposure_by_product": exp,
        "top_risk_positions": top,
        "count": len(rows),
    }


def margins_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    if isinstance(payload.get("data"), dict):
        payload = payload.get("data") or payload
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
    if isinstance(raw_payload, list):
        rows = raw_payload
    elif isinstance(raw_payload, dict) and isinstance(raw_payload.get("data"), list):
        rows = raw_payload.get("data") or []
    else:
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

def tavily_search_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    query = str(payload.get("query") or payload.get("q") or "") if isinstance(payload, dict) else ""
    query = query.strip()
    query_hash = hash_identifier(settings, query)[:16] if query else ""

    results_raw: list[Any] = []
    if isinstance(payload.get("results"), list):
        results_raw = payload.get("results")  # type: ignore[assignment]
    elif isinstance(payload.get("data"), dict) and isinstance((payload.get("data") or {}).get("results"), list):
        results_raw = (payload.get("data") or {}).get("results")  # type: ignore[assignment]

    out_rows: list[dict[str, Any]] = []
    for r in results_raw[:8]:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip() or None
        snippet = str(r.get("content") or r.get("snippet") or r.get("summary") or "").strip() or None
        url = str(r.get("url") or r.get("link") or "").strip() or None
        domain = None
        if url:
            try:
                domain = (urlparse(url).netloc or "").lower() or None
            except Exception:
                domain = None
        published = (
            str(r.get("published_date") or r.get("published") or r.get("date") or r.get("publishedDate") or "").strip() or None
        )
        out_rows.append(
            {
                "title": title,
                "snippet": (snippet[:400] + "…") if snippet and len(snippet) > 401 else snippet,
                "source_domain": domain,
                "published": published,
            }
        )

    return {
        "schema": "tavily_search_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "query_hash": query_hash,
        "results": out_rows,
        "count": len(out_rows),
    }

def _normalize_quotes_map(payload: Any) -> dict[str, dict[str, Any]]:
    """Normalize common broker quote payload shapes into a {symbol: quote_dict} mapping.

    This MUST remain PII-safe: market data only.
    """
    p = payload
    if isinstance(p, dict) and isinstance(p.get("data"), dict):
        p = p.get("data") or {}

    out: dict[str, dict[str, Any]] = {}
    if isinstance(p, dict):
        for k, v in p.items():
            if not isinstance(v, dict):
                continue
            key = str(k or "").strip()
            if not key:
                # Try to recover from row-shaped payloads.
                ex = str(v.get("exchange") or "").strip().upper()
                ts = str(v.get("tradingsymbol") or v.get("symbol") or "").strip().upper()
                if ex and ts:
                    key = f"{ex}:{ts}"
            if not key:
                continue
            out[key] = v
        return out

    if isinstance(p, list):
        for r in p:
            if not isinstance(r, dict):
                continue
            ex = str(r.get("exchange") or "").strip().upper()
            ts = str(r.get("tradingsymbol") or r.get("symbol") or "").strip().upper()
            if not (ex and ts):
                continue
            out[f"{ex}:{ts}"] = r
    return out


def quotes_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    quotes_map = _normalize_quotes_map(raw_payload)
    symbols = sorted({s for s in quotes_map.keys() if s})

    rows: list[dict[str, Any]] = []
    for sym in symbols[:25]:
        q = quotes_map.get(sym) or {}
        ltp = _as_float(q.get("last_price")) or _as_float(q.get("ltp")) or _as_float(q.get("last")) or _as_float(q.get("price"))
        close = None
        if isinstance(q.get("ohlc"), dict):
            close = _as_float((q.get("ohlc") or {}).get("close"))
        close = close or _as_float(q.get("close")) or _as_float(q.get("prev_close")) or _as_float(q.get("previous_close"))
        change = (float(ltp) - float(close)) if (ltp is not None and close is not None) else None
        change_pct = (change / float(close) * 100.0) if (change is not None and close is not None and float(close) != 0.0) else None
        rows.append(
            {
                "symbol": sym,
                "ltp": float(ltp) if ltp is not None else None,
                "prev_close": float(close) if close is not None else None,
                "change": float(change) if change is not None else None,
                "change_pct": float(change_pct) if change_pct is not None else None,
            }
        )

    return {
        "schema": "quotes_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "symbols": symbols[:200],
        "quotes": rows,
        "count": len(rows),
    }


def ltp_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    # Most MCP servers reuse the same shape as get_quotes; keep it consistent.
    out = quotes_safe_summary(settings, raw_payload)
    out["schema"] = "ltp_safe_summary.v1"
    return out


def ohlc_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    quotes_map = _normalize_quotes_map(raw_payload)
    symbols = sorted({s for s in quotes_map.keys() if s})

    rows: list[dict[str, Any]] = []
    for sym in symbols[:25]:
        q = quotes_map.get(sym) or {}
        ohlc = q.get("ohlc") if isinstance(q.get("ohlc"), dict) else {}
        rows.append(
            {
                "symbol": sym,
                "open": _as_float((ohlc or {}).get("open")) or _as_float(q.get("open")),
                "high": _as_float((ohlc or {}).get("high")) or _as_float(q.get("high")),
                "low": _as_float((ohlc or {}).get("low")) or _as_float(q.get("low")),
                "close": _as_float((ohlc or {}).get("close")) or _as_float(q.get("close")),
                "ltp": _as_float(q.get("last_price")) or _as_float(q.get("ltp")),
            }
        )

    return {
        "schema": "ohlc_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "symbols": symbols[:200],
        "ohlc": rows,
        "count": len(rows),
    }


def historical_data_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    # Historical payloads can be large. Return compact summary + tail sample only.
    p = raw_payload
    if isinstance(p, dict) and isinstance(p.get("data"), (list, dict)):
        p = p.get("data")
    rows: list[dict[str, Any]] = []
    if isinstance(p, list):
        for r in p:
            if isinstance(r, dict):
                rows.append(r)
            elif isinstance(r, (list, tuple)) and len(r) >= 5:
                # Common OHLCV list format: [ts, o, h, l, c, v?]
                rows.append({"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5] if len(r) > 5 else None})
    elif isinstance(p, dict) and isinstance(p.get("candles"), list):
        for r in p.get("candles") or []:
            if isinstance(r, dict):
                rows.append(r)
            elif isinstance(r, (list, tuple)) and len(r) >= 5:
                rows.append({"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5] if len(r) > 5 else None})

    closes = [_as_float(r.get("close")) for r in rows if isinstance(r, dict)]
    closes2 = [c for c in closes if c is not None]
    last_close = closes2[-1] if closes2 else None
    min_close = min(closes2) if closes2 else None
    max_close = max(closes2) if closes2 else None

    tail = []
    for r in rows[-10:]:
        if not isinstance(r, dict):
            continue
        tail.append(
            {
                "ts": str(r.get("ts") or r.get("date") or r.get("timestamp") or ""),
                "open": _as_float(r.get("open")),
                "high": _as_float(r.get("high")),
                "low": _as_float(r.get("low")),
                "close": _as_float(r.get("close")),
                "volume": _as_float(r.get("volume")),
            }
        )

    return {
        "schema": "historical_data_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "count": len(rows),
        "stats": {"last_close": last_close, "min_close": min_close, "max_close": max_close},
        "tail": tail,
    }


def search_instruments_safe_summary(settings: Settings, raw_payload: Any) -> dict[str, Any]:  # noqa: ARG001
    p = raw_payload
    if isinstance(p, dict) and isinstance(p.get("data"), list):
        p = p.get("data") or []
    elif isinstance(p, dict) and isinstance(p.get("data"), dict) and isinstance((p.get("data") or {}).get("instruments"), list):
        p = (p.get("data") or {}).get("instruments") or []

    rows: list[dict[str, Any]] = []
    if isinstance(p, list):
        for r in p[:20]:
            if not isinstance(r, dict):
                continue
            ex = str(r.get("exchange") or "").strip().upper() or None
            ts = str(r.get("tradingsymbol") or r.get("symbol") or "").strip().upper() or None
            name = str(r.get("name") or "").strip() or None
            seg = str(r.get("segment") or r.get("exchange_segment") or "").strip().upper() or None
            if ex and ts:
                sym = f"{ex}:{ts}"
            else:
                sym = ts or None
            if not sym:
                continue
            rows.append({"symbol": sym, "name": name, "segment": seg})

    return {
        "schema": "search_instruments_safe_summary.v1",
        "as_of_ts": _now_iso(),
        "matches": rows,
        "count": len(rows),
    }


Summarizer = Callable[[Settings, Any], dict[str, Any]]


_REGISTRY: dict[str, Summarizer] = {
    "get_holdings": holdings_safe_summary,
    "get_positions": positions_safe_summary,
    "get_margins": margins_safe_summary,
    "get_orders": orders_safe_summary,
    # Market data tools (read-only).
    "get_quotes": quotes_safe_summary,
    "get_ltp": ltp_safe_summary,
    "get_ohlc": ohlc_safe_summary,
    "get_historical_data": historical_data_safe_summary,
    "search_instruments": search_instruments_safe_summary,
    # Internal tools
    "propose_trade_plan": propose_trade_plan_safe_summary,
    "execute_trade_plan": execute_trade_plan_safe_summary,
    # External tools
    "tavily_search": tavily_search_safe_summary,
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
