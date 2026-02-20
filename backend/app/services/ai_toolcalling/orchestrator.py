from __future__ import annotations

import json
import re
import asyncio
import hashlib
from datetime import UTC, datetime
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai.safety.payload_inspector import PayloadInspectionError, inspect_llm_payload
from app.ai.safety.safe_summary_registry import (
    SafeSummaryError,
    summarize_tool_for_llm,
    tool_has_safe_summary,
)
from app.core.config import Settings
from app.models import Candle
from app.schemas.ai_trading_manager import DecisionToolCall, Quote, TradeIntent
from app.services.ai.provider_registry import get_provider
from app.services.ai.active_config import get_active_config
from app.services.ai.provider_keys import decrypt_key_value, get_key
from app.services.ai.temperature import effective_temperature
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source
from app.services.ai_trading_manager.ai_settings_config import is_execution_hard_disabled
from app.services.ai_trading_manager.execution.engine import ExecutionEngine
from app.services.ai_trading_manager.execution.idempotency_store import IdempotencyStore
from app.services.ai_trading_manager.execution.post_trade_reconcile import post_trade_reconcile
from app.services.ai_trading_manager.feature_flags import require_ai_assistant_enabled
from app.services.ai_trading_manager.ledger_snapshot import build_ledger_snapshot
from app.services.ai_trading_manager.operator_payload_store import persist_operator_payload
from app.services.ai_trading_manager.plan_engine import new_plan_from_intent, normalize_trade_plan
from app.services.ai_trading_manager.playbooks import get_trade_plan, upsert_trade_plan
from app.services.ai_trading_manager.manage_playbook_engine import IntentContext, evaluate_playbook_pretrade
from app.services.ai_trading_manager.riskgate.engine import evaluate_riskgate
from app.services.ai_trading_manager.sizing import extract_equity_value, suggest_qty
from app.services.kite_mcp.secrets import get_auth_session_id
from app.services.kite_mcp.session_manager import kite_mcp_sessions
from app.services.kite_mcp.snapshot import fetch_kite_mcp_snapshot
from app.services.kite_mcp.trade import KiteMcpTradeClient
from app.services.system_events import record_system_event
from app.models.ai_trading_manager import AiTmPositionShadow

from .mcp_tools import hash_tool_definitions, mcp_tools_to_openai_tools, tool_result_preview
from .openai_toolcaller import OpenAiChatError, openai_chat_with_tools
from .policy import classify_tool, evaluate_tool_policy, tool_lookup_map
from .redaction import redact_for_llm
from .tools_cache import get_tools_cached


@dataclass(frozen=True)
class ToolCallLog:
    name: str
    arguments: Dict[str, Any]
    status: str  # ok|blocked|error
    duration_ms: int
    result_preview: str
    error: str | None = None


@dataclass(frozen=True)
class ChatResult:
    assistant_message: str
    decision_id: str
    tool_calls: List[ToolCallLog]

@dataclass(frozen=True)
class _DirectPortfolioRequest:
    want_holdings: bool
    want_positions: bool
    want_summary: bool
    top_n: int | None = None


def _corr() -> str:
    return uuid4().hex


def _safe_prompt_audit(prompt: str, *, do_not_send_pii: bool) -> dict[str, Any]:
    p = prompt or ""
    h = hashlib.sha256(p.encode("utf-8")).hexdigest()
    if do_not_send_pii:
        return {"prompt_hash": h, "prompt_len": len(p)}
    preview = p.strip().replace("\n", " ")
    if len(preview) > 120:
        preview = preview[:120] + "…"
    return {"prompt_hash": h, "prompt_len": len(p), "prompt_preview": preview}


def _minimal_llm_context(ui_context: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Whitelisted UI context for the LLM (least-data-by-design)."""
    if not isinstance(ui_context, dict):
        return None
    out: dict[str, Any] = {}
    page = ui_context.get("page")
    if isinstance(page, str) and page.strip():
        out["page"] = page.strip()
    # Intentionally omit identifiers, broker ids, auth/session info, and raw UI state.
    return out or None


def _minimal_attachments_for_llm(attachments: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    """Whitelisted attachment summaries for the LLM."""
    out: list[dict[str, Any]] = []
    for a in attachments or []:
        if not isinstance(a, dict):
            continue
        summary = a.get("summary") if isinstance(a.get("summary"), dict) else {}
        out.append(
            {
                "file_id": str(a.get("file_id") or ""),
                "filename": str(a.get("filename") or ""),
                "summary": {
                    "kind": str(summary.get("kind") or ""),
                    "row_count": int(summary.get("row_count") or 0),
                    "columns": list(summary.get("columns") or []),
                    # preview_rows may contain PII; payload inspector will fail-closed if present.
                    "preview_rows": summary.get("preview_rows") or [],
                    "sheets": list(summary.get("sheets") or []) if summary.get("sheets") else None,
                    "active_sheet": summary.get("active_sheet"),
                },
            }
        )
    return out


def _parse_direct_portfolio_request(msg: str) -> _DirectPortfolioRequest | None:
    m = (msg or "").strip().lower()
    if not m:
        return None

    # Trigger only on explicit "show/list/fetch" style requests.
    if not any(x in m for x in ("show", "list", "display", "fetch")):
        return None

    want_holdings = any(x in m for x in ("holding", "cnc", "delivery", "portfolio"))
    want_positions = any(x in m for x in ("position", "net"))
    want_summary = any(x in m for x in ("summarize", "summary", "exposure", "risk"))

    if "holdings" in m and "positions" in m:
        want_holdings = True
        want_positions = True

    if not (want_holdings or want_positions):
        return None

    # "portfolio" implies both unless user narrowed explicitly.
    if "portfolio" in m and not ("holding" in m or "position" in m or "net" in m):
        want_holdings = True
        want_positions = True

    top_n = None
    mt = re.search(r"\\btop\\s+(\\d{1,3})\\b", m)
    if mt:
        try:
            n = int(mt.group(1))
            if 1 <= n <= 50:
                top_n = n
        except Exception:
            top_n = None

    return _DirectPortfolioRequest(
        want_holdings=bool(want_holdings),
        want_positions=bool(want_positions),
        want_summary=bool(want_summary),
        top_n=top_n,
    )


def _extract_tool_text(res: dict[str, Any]) -> str:
    content = res.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return str(first.get("text") or "")
    return ""


def _extract_tool_json(res: dict[str, Any]) -> Any:
    text = _extract_tool_text(res)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text


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
        qty = _as_float(r.get("quantity")) or _as_float(r.get("qty")) or 0.0
        avg = _as_float(r.get("average_price")) or _as_float(r.get("avg_price"))
        ltp = _as_float(r.get("last_price")) or _as_float(r.get("ltp"))
        value = (ltp or 0.0) * qty if ltp is not None else None
        invested = (avg or 0.0) * qty if avg is not None else None
        current = (ltp or 0.0) * qty if ltp is not None else None
        pnl = _as_float(r.get("pnl"))
        if pnl is None and invested is not None and current is not None:
            pnl = current - invested
        out.append(
            {
                "symbol": sym,
                "product": str(r.get("product") or "CNC").strip().upper(),
                "qty": int(qty) if float(qty).is_integer() else qty,
                "value": f"{value:.2f}" if isinstance(value, (int, float)) else ("" if value is None else str(value)),
                "avg": f"{avg:.2f}" if isinstance(avg, (int, float)) else ("" if avg is None else str(avg)),
                "ltp": f"{ltp:.2f}" if isinstance(ltp, (int, float)) else ("" if ltp is None else str(ltp)),
                "pnl": f"{pnl:.2f}" if isinstance(pnl, (int, float)) else ("" if pnl is None else str(pnl)),
            }
        )
    return [r for r in out if r.get("symbol")]


def _positions_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("net"), list):
        rows = [r for r in payload.get("net") if isinstance(r, dict)]
    elif isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    out: list[dict[str, Any]] = []
    for r in rows:
        sym = str(r.get("tradingsymbol") or r.get("symbol") or "").strip().upper()
        qty = _as_float(r.get("quantity")) or _as_float(r.get("qty")) or 0.0
        if qty == 0:
            continue
        avg = _as_float(r.get("average_price")) or _as_float(r.get("avg_price"))
        ltp = _as_float(r.get("last_price")) or _as_float(r.get("ltp"))
        notional = abs(qty) * (ltp if ltp is not None else (avg or 0.0))
        pnl = _as_float(r.get("pnl")) or _as_float(r.get("pnl_unrealised")) or _as_float(r.get("pnl_unrealized"))
        out.append(
            {
                "symbol": sym,
                "product": str(r.get("product") or "CNC").strip().upper(),
                "qty": int(qty) if float(qty).is_integer() else qty,
                "value": (
                    f"{notional:.2f}"
                    if isinstance(notional, (int, float))
                    else ("" if notional is None else str(notional))
                ),
                "avg": f"{avg:.2f}" if isinstance(avg, (int, float)) else ("" if avg is None else str(avg)),
                "ltp": f"{ltp:.2f}" if isinstance(ltp, (int, float)) else ("" if ltp is None else str(ltp)),
                "pnl": f"{pnl:.2f}" if isinstance(pnl, (int, float)) else ("" if pnl is None else str(pnl)),
            }
        )
    return [r for r in out if r.get("symbol")]


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], *, limit: int = 500) -> str:
    used = rows[:limit]
    header = "| " + " | ".join([c[0] for c in columns]) + " |"
    sep = "| " + " | ".join(["---" for _ in columns]) + " |"
    lines = [header, sep]
    for r in used:
        vals: list[str] = []
        for _label, key in columns:
            v = r.get(key)
            s = "" if v is None else str(v)
            s = s.replace("\n", " ").strip()
            vals.append(s)
        lines.append("| " + " | ".join(vals) + " |")
    extra = len(rows) - len(used)
    if extra > 0:
        lines.append("")
        lines.append(f"_({extra} more rows not shown)_")
    return "\n".join(lines)


def _llm_summary_count(summary: Any) -> int | None:
    if not isinstance(summary, dict):
        return None
    totals = summary.get("totals")
    if isinstance(totals, dict) and isinstance(totals.get("count"), int):
        return int(totals.get("count") or 0)
    if isinstance(summary.get("count"), int):
        return int(summary.get("count") or 0)
    return None


def _compact_json(value: Any, *, max_chars: int) -> str:
    s = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
    if len(s) > max_chars:
        return s[:max_chars] + "…"
    return s


async def run_chat(
    db: Session,
    settings: Settings,
    *,
    account_id: str,
    user_message: str,
    authorization_message_id: str | None = None,
    attachments: List[Dict[str, Any]] | None = None,
    ui_context: Dict[str, Any] | None = None,
    correlation_id: str | None = None,
    event_cb: Callable[[dict[str, object]], Awaitable[None]] | None = None,
    stream_assistant: bool = False,
) -> ChatResult:
    require_ai_assistant_enabled(db, settings)
    corr = correlation_id or _corr()
    direct_req = _parse_direct_portfolio_request(user_message)

    ai_cfg, _src = get_active_config(db, settings)
    if not ai_cfg.enabled:
        raise HTTPException(status_code=403, detail="AI provider is disabled. Enable it in Settings → AI.")
    if (ai_cfg.provider or "").strip().lower() != "openai":
        raise HTTPException(status_code=400, detail="Tool-calling MVP currently supports OpenAI provider only.")
    if not ai_cfg.model:
        raise HTTPException(status_code=400, detail="AI model is not set. Configure it in Settings → AI.")
    if ai_cfg.active_key_id is None:
        raise HTTPException(status_code=400, detail="No OpenAI key selected. Add/select a key in Settings → AI.")

    key_row = get_key(db, key_id=int(ai_cfg.active_key_id), user_id=None)
    if key_row is None:
        raise HTTPException(status_code=400, detail="Selected OpenAI key not found.")
    api_key = decrypt_key_value(settings, key_row)

    tm_cfg, _tm_src = get_ai_settings_with_source(db, settings)
    if not tm_cfg.feature_flags.kite_mcp_enabled or not tm_cfg.kite_mcp.server_url:
        raise HTTPException(
            status_code=400,
            detail="Kite MCP is not enabled/configured. Configure it in Settings → AI.",
        )

    auth_sid = get_auth_session_id(db, settings)
    session = await kite_mcp_sessions.get_session(server_url=tm_cfg.kite_mcp.server_url, auth_session_id=auth_sid)
    await session.ensure_initialized()

    cached, refreshed = await get_tools_cached(server_url=tm_cfg.kite_mcp.server_url, session=session, ttl_seconds=300)
    # Only expose safe (read-only) MCP tools to the LLM; trade tools are routed
    # exclusively through ST internal execution, gated by policy + flags.
    safe_mcp_tools = [t for t in cached.mcp_tools if classify_tool(str(t.get("name") or ""), t) == "read"]
    # PII Safety Layer: only expose tools that have deterministic safe summaries.
    llm_mcp_tools = [t for t in safe_mcp_tools if tool_has_safe_summary(str(t.get("name") or ""))]

    internal_tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "propose_trade_plan",
                "description": "Create a structured TradePlan proposal (no broker execution).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbols": {"type": "array", "items": {"type": "string"}},
                        "side": {"type": "string", "enum": ["BUY", "SELL"]},
                        "product": {"type": "string", "enum": ["CNC", "MIS"]},
                        "risk_budget_pct": {"type": "number"},
                        "atr_period": {"type": "integer", "default": 14},
                        "atr_multiplier": {"type": "number", "default": 2.0},
                    },
                    "required": ["symbols", "side", "product"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_trade_plan",
                "description": "Execute a previously proposed TradePlan (policy-gated, idempotent).",
                "parameters": {
                    "type": "object",
                    "properties": {"plan_id": {"type": "string"}},
                    "required": ["plan_id"],
                },
            },
        },
    ]

    openai_tools = mcp_tools_to_openai_tools(llm_mcp_tools) + internal_tools
    tools_hash = hash_tool_definitions(openai_tools)
    # Keep full lookup for policy checks; models may still hallucinate names.
    tools_by_name = tool_lookup_map(cached.mcp_tools)

    if refreshed:
        record_system_event(
            db,
            level="INFO",
            category="AI_ORCH",
            message="AI tool list refreshed.",
            correlation_id=corr,
            details={
                "event_type": "AI_TOOL_LIST_REFRESHED",
                "tools_hash": tools_hash,
                "safe_count": len(llm_mcp_tools),
                "total_count": len(cached.mcp_tools),
            },
        )

    record_system_event(
        db,
        level="INFO",
        category="AI_ORCH",
        message="AI chat requested.",
        correlation_id=corr,
        details={
            "event_type": "AI_CHAT_REQUESTED",
            "account_id": account_id,
            "provider": ai_cfg.provider,
            "model": ai_cfg.model,
            "tools_hash": tools_hash,
            "authorization_message_id": authorization_message_id,
            **_safe_prompt_audit(user_message, do_not_send_pii=bool(ai_cfg.do_not_send_pii)),
        },
    )

    system_prompt = (
        "You are SigmaTrader's AI Trading Manager. "
        "You can call tools to read broker-truth portfolio data via Kite MCP. "
        "Only call tools that help answer the user's question. "
        "Important: in Kite, 'holdings' (delivery/CNC) are different from 'positions' (net open/intraday). "
        "If the user asks for 'positions' but expects their portfolio, you likely need get_holdings too. "
        "For trading intents, first call propose_trade_plan. "
        "Only call execute_trade_plan when the user explicitly asks to execute.\n\n"
        "Never call broker order tools directly. Execution is policy-gated and may be vetoed.\n\n"
        "When you answer, be concise and structured with short sections."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    llm_ctx = _minimal_llm_context(ui_context)
    if llm_ctx:
        messages.append({"role": "system", "content": f"Context (json): {json.dumps(llm_ctx, ensure_ascii=False)}"})
    if attachments:
        attachments_json = json.dumps(_minimal_attachments_for_llm(attachments), ensure_ascii=False)
        messages.append(
            {
                "role": "system",
                "content": f"Attachments (summaries json): {attachments_json}",
            }
        )
    messages.append({"role": "user", "content": user_message})

    tool_logs: List[ToolCallLog] = []
    trace = audit_store.new_decision_trace(
        correlation_id=corr,
        account_id=account_id,
        user_message=user_message,
        inputs_used={
            "provider": ai_cfg.provider,
            "model": ai_cfg.model,
            "tools_hash": tools_hash,
            "kite_mcp_server_url": tm_cfg.kite_mcp.server_url,
            "authorization_message_id": authorization_message_id,
            "attachments": [
                {
                    "file_id": str(a.get("file_id") or ""),
                    "filename": str(a.get("filename") or ""),
                    "kind": str((a.get("summary") or {}).get("kind") or ""),
                    "row_count": int((a.get("summary") or {}).get("row_count") or 0),
                    "columns_count": len((a.get("summary") or {}).get("columns") or []),
                }
                for a in (attachments or [])
                if isinstance(a, dict)
            ],
        },
    )
    if event_cb is not None:
        try:
            await event_cb({"type": "decision", "decision_id": trace.decision_id, "correlation_id": corr})
        except Exception:
            pass

    if direct_req is not None:
        async def _call_json(name: str) -> Any:
            t0 = time.perf_counter()
            tool_call_id = uuid4().hex
            res = await session.tools_call(name=name, arguments={})
            if isinstance(res, dict) and res.get("isError") is True:
                raise RuntimeError(_extract_tool_text(res) or f"{name} failed.")
            payload = _extract_tool_json(res) if isinstance(res, dict) else None
            duration_ms = int((time.perf_counter() - t0) * 1000)
            meta = persist_operator_payload(
                db,
                decision_id=trace.decision_id,
                tool_name=name,
                tool_call_id=tool_call_id,
                account_id=account_id,
                user_id=None,
                payload=payload,
            )
            llm_summary = summarize_tool_for_llm(settings, tool_name=name, operator_payload=payload)
            preview = tool_result_preview(llm_summary, max_chars=1200)
            tool_logs.append(
                ToolCallLog(
                    name=name,
                    arguments={},
                    status="ok",
                    duration_ms=duration_ms,
                    result_preview=preview,
                )
            )
            trace.tools_called.append(
                DecisionToolCall(
                    tool_name=name,
                    input_summary={},
                    output_summary={"preview": preview},
                    duration_ms=duration_ms,
                    operator_payload_meta=meta,
                    llm_summary=llm_summary,
                    broker_raw_count=int(meta.get("items_count") or 0),
                    llm_summary_count=_llm_summary_count(llm_summary),
                )
            )
            if event_cb is not None:
                try:
                    await event_cb(
                        {
                            "type": "tool_call",
                            "name": name,
                            "arguments": {},
                            "status": "ok",
                            "duration_ms": duration_ms,
                            "result_preview": preview,
                        }
                    )
                except Exception:
                    pass
            return payload

        holdings_payload = None
        positions_payload = None
        try:
            if direct_req.want_holdings:
                holdings_payload = await _call_json("get_holdings")
            if direct_req.want_positions:
                positions_payload = await _call_json("get_positions")
        except Exception as exc:
            final_text = f"Failed to fetch portfolio data from Kite MCP: {str(exc) or 'unknown error'}"
            trace.final_outcome = {"assistant_message": final_text, "tool_calls": [t.__dict__ for t in tool_logs]}
            trace.explanations = []
            audit_store.persist_decision_trace(db, trace, user_id=None)
            return ChatResult(assistant_message=final_text, decision_id=trace.decision_id, tool_calls=tool_logs)

        holdings_rows = _holdings_rows(holdings_payload) if holdings_payload is not None else []
        positions_rows = _positions_rows(positions_payload) if positions_payload is not None else []
        # Update trace counters so UI can show "broker raw vs UI rendered vs LLM summary" clearly.
        for t in trace.tools_called:
            if t.tool_name == "get_holdings" and t.ui_rendered_count is None:
                t.ui_rendered_count = len(holdings_rows)
            if t.tool_name == "get_positions" and t.ui_rendered_count is None:
                t.ui_rendered_count = len(positions_rows)

        parts: list[str] = []
        if direct_req.want_holdings:
            used_holdings = holdings_rows
            if direct_req.top_n:
                def _val(r: dict[str, Any]) -> float:
                    try:
                        return float(str(r.get("value") or 0.0))
                    except Exception:
                        return 0.0

                used_holdings = sorted(holdings_rows, key=_val, reverse=True)[: int(direct_req.top_n)]
            suffix = f" — top {direct_req.top_n}" if direct_req.top_n else ""
            parts.append(f"## Holdings (Delivery/CNC){suffix} — {len(used_holdings)}")
            parts.append(
                _md_table(
                    used_holdings,
                    [
                        ("Symbol", "symbol"),
                        ("Qty", "qty"),
                        ("Value", "value"),
                        ("Avg", "avg"),
                        ("LTP", "ltp"),
                        ("P&L", "pnl"),
                    ],
                    limit=500,
                )
            )
        if direct_req.want_positions:
            used_positions = positions_rows
            if direct_req.top_n:
                def _val2(r: dict[str, Any]) -> float:
                    try:
                        return float(str(r.get("value") or 0.0))
                    except Exception:
                        return 0.0

                used_positions = sorted(positions_rows, key=_val2, reverse=True)[: int(direct_req.top_n)]
            suffix2 = f" — top {direct_req.top_n}" if direct_req.top_n else ""
            parts.append(f"## Positions (Net){suffix2} — {len(used_positions)}")
            parts.append(
                _md_table(
                    used_positions,
                    [
                        ("Symbol", "symbol"),
                        ("Product", "product"),
                        ("Qty", "qty"),
                        ("Value", "value"),
                        ("Avg", "avg"),
                        ("LTP", "ltp"),
                        ("P&L", "pnl"),
                    ],
                    limit=500,
                )
            )

        if direct_req.want_summary:
            def _sum_pnl(rows: list[dict[str, Any]]) -> float:
                tot = 0.0
                for r in rows:
                    v = _as_float(r.get("pnl"))
                    if v is not None:
                        tot += float(v)
                return tot

            parts.append("## Exposure summary (deterministic)")
            parts.append(f"- Holdings count: {len(holdings_rows)}")
            parts.append(f"- Positions count: {len(positions_rows)}")
            if holdings_rows:
                parts.append(f"- Holdings P&L (sum): {_sum_pnl(holdings_rows):.2f}")
            if positions_rows:
                parts.append(f"- Positions P&L (sum): {_sum_pnl(positions_rows):.2f}")

        final_text = "\n\n".join(parts).strip() or "No data returned."
        if event_cb is not None and stream_assistant:
            try:
                chunk_size = 120
                for i in range(0, len(final_text), chunk_size):
                    await event_cb({"type": "assistant_delta", "text": final_text[i : i + chunk_size]})
            except Exception:
                pass
        trace.final_outcome = {
            "assistant_message": final_text,
            "tool_calls": [t.__dict__ for t in tool_logs],
            "portfolio": {"holdings_count": len(holdings_rows), "positions_count": len(positions_rows)},
        }
        trace.explanations = []
        audit_store.persist_decision_trace(db, trace, user_id=None)
        return ChatResult(assistant_message=final_text, decision_id=trace.decision_id, tool_calls=tool_logs)

    structured: dict[str, Any] = {}
    if authorization_message_id:
        structured["authorization_message_id"] = authorization_message_id

    def _is_explicit_execute(msg: str) -> bool:
        m = (msg or "").lower()
        if any(x in m for x in ("plan", "proposal", "what if", "simulate")):
            return False
        return bool(re.search(r"\\b(buy|sell|execute|place|go\\s+ahead|enter)\\b", m))

    def _hash_payload(value: Any) -> str:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _latest_close(symbol: str, *, exchange: str = "NSE", timeframe: str = "1d") -> float | None:
        row = (
            db.execute(
                select(Candle.close)
                .where(Candle.symbol == symbol, Candle.exchange == exchange, Candle.timeframe == timeframe)
                .order_by(desc(Candle.ts))
                .limit(1)
            )
            .scalar_one_or_none()
        )
        try:
            return float(row) if row is not None else None
        except Exception:
            return None

    def _compute_atr(symbol: str, *, exchange: str = "NSE", timeframe: str = "1d", period: int = 14) -> float | None:
        n = int(period)
        if n <= 1:
            return None
        rows = (
            db.execute(
                select(Candle.high, Candle.low, Candle.close)
                .where(Candle.symbol == symbol, Candle.exchange == exchange, Candle.timeframe == timeframe)
                .order_by(desc(Candle.ts))
                .limit(n + 1)
            )
            .all()
        )
        if len(rows) < (n + 1):
            return None
        # rows are newest-first; compute TR in chronological order for stability.
        rows2 = list(reversed([(float(high), float(low), float(close)) for high, low, close in rows]))
        prev_close = rows2[0][2]
        trs: list[float] = []
        for high, low, close in rows2[1:]:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(float(tr))
            prev_close = close
        if not trs:
            return None
        return float(sum(trs) / float(len(trs)))

    prov = get_provider(str(ai_cfg.provider or ""))
    provider_kind = str(getattr(prov, "kind", "") or "remote").lower()
    is_remote_provider = provider_kind == "remote"

    final_text = ""
    max_iters = 6
    for _i in range(max_iters):
        # Enforce PII-safe outbound payload for remote providers (fail-closed).
        if is_remote_provider:
            try:
                inspect_llm_payload({"model": str(ai_cfg.model), "messages": messages, "tools": openai_tools})
            except PayloadInspectionError as exc:
                # Do not attempt a remote call if payload contains forbidden keys/patterns.
                findings = [{"path": f.path, "kind": f.kind, "detail": f.detail} for f in (exc.findings or [])][:10]
                final_text = (
                    "Blocked sending sensitive data to a remote LLM by PII safety policy. "
                    "Use a local provider (Ollama/LM Studio) or remove sensitive content and retry."
                )
                trace.final_outcome = {
                    "assistant_message": final_text,
                    "blocked_by": "PII_POLICY",
                    "findings": findings,
                }
                trace.explanations = ["PII_POLICY_BLOCKED_OUTBOUND_LLM_PAYLOAD"]
                record_system_event(
                    db,
                    level="WARNING",
                    category="AI_ORCH",
                    message="Outbound LLM request blocked by PII policy.",
                    correlation_id=corr,
                    details={
                        "event_type": "AI_PII_BLOCKED",
                        "provider": str(ai_cfg.provider),
                        "model": str(ai_cfg.model),
                        "findings": findings,
                    },
                )
                break
        try:
            turn = await openai_chat_with_tools(
                api_key=api_key,
                model=str(ai_cfg.model),
                messages=messages,
                tools=openai_tools,
                timeout_seconds=30,
                max_tokens=ai_cfg.limits.max_tokens_per_request,
                temperature=effective_temperature(
                    provider_id=str(ai_cfg.provider),
                    model=str(ai_cfg.model),
                    configured=getattr(ai_cfg, "temperature", None),
                ),
            )
        except OpenAiChatError as exc:
            final_text = f"AI provider error: {exc}"
            break

        if not turn.tool_calls:
            final_text = (turn.content or "").strip()
            break

        # Add assistant tool call turn into message history (OpenAI expects this).
        messages.append(
            {
                "role": "assistant",
                "content": turn.content or "",
                "tool_calls": [
                    {
                        "id": tc.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": _compact_json(redact_for_llm(tc.arguments or {}), max_chars=4000),
                        },
                    }
                    for tc in turn.tool_calls
                ],
            }
        )

        pii_abort_message: str | None = None
        for tc in turn.tool_calls:
            t0 = time.perf_counter()
            # Internal tools: handled by SigmaTrader (not MCP).
            if tc.name in {"propose_trade_plan", "execute_trade_plan"}:
                duration_ms = 0
                try:
                    if tc.name == "propose_trade_plan":
                        args = tc.arguments or {}
                        symbols = args.get("symbols") or []
                        if isinstance(symbols, str):
                            symbols = [symbols]
                        symbols2 = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
                        side = str(args.get("side") or "").strip().upper()
                        product = str(args.get("product") or "CNC").strip().upper()
                        risk_budget_pct = args.get("risk_budget_pct")
                        try:
                            rb = float(risk_budget_pct) if risk_budget_pct is not None else None
                        except Exception:
                            rb = None
                        atr_period = int(args.get("atr_period") or 14)
                        atr_mult = float(args.get("atr_multiplier") or 2.0)

                        if not symbols2 or side not in {"BUY", "SELL"} or product not in {"CNC", "MIS"}:
                            raise ValueError("invalid trade plan inputs")

                        # Deterministic market data from DB candles.
                        sym0 = symbols2[0]
                        entry_px = _latest_close(sym0)
                        atr = _compute_atr(sym0, period=atr_period)
                        if entry_px is None or atr is None or entry_px <= 0 or atr <= 0:
                            raise ValueError("missing candle data for ATR/entry price")

                        if side == "BUY":
                            stop_px = float(entry_px) - (float(atr) * float(atr_mult))
                        else:
                            stop_px = float(entry_px) + (float(atr) * float(atr_mult))

                        # Size from broker equity if possible.
                        qty = 1
                        qty_metrics: dict[str, Any] = {}
                        if rb and rb > 0:
                            broker_snap = await fetch_kite_mcp_snapshot(db, settings, account_id=account_id)
                            equity = extract_equity_value(broker_snap.margins or {}) or 0.0
                            if equity > 0:
                                qty, qty_metrics = suggest_qty(
                                    entry_price=float(entry_px),
                                    stop_price=float(stop_px),
                                    risk_budget_pct=float(rb),
                                    equity_value=float(equity),
                                )

                        intent = TradeIntent(
                            symbols=symbols2,
                            side=side,  # type: ignore[arg-type]
                            product=product,  # type: ignore[arg-type]
                            constraints={"qty": int(qty)},
                            risk_budget_pct=rb,
                        )
                        plan = normalize_trade_plan(new_plan_from_intent(intent))
                        plan = plan.model_copy(
                            update={
                                "risk_model": {
                                    "stop_type": "ATR",
                                    "atr_period": atr_period,
                                    "atr": float(atr),
                                    "atr_multiplier": float(atr_mult),
                                    "entry_price": float(entry_px),
                                    "stop_price": float(stop_px),
                                    "qty_metrics": qty_metrics,
                                }
                            }
                        )
                        upsert_trade_plan(db, plan=plan, user_id=None, account_id=account_id)

                        full_plan = plan.model_dump(mode="json")
                        plan_hash = _hash_payload(full_plan)
                        out = {
                            "plan_id": plan.plan_id,
                            "plan_hash": plan_hash,
                            "plan": {
                                "plan_id": plan.plan_id,
                                "intent": full_plan.get("intent"),
                                "order_skeleton": full_plan.get("order_skeleton"),
                                "risk_model": {
                                    "stop_type": "ATR",
                                    "atr_period": atr_period,
                                    "atr": float(atr),
                                    "atr_multiplier": float(atr_mult),
                                    "entry_price": float(entry_px),
                                    "stop_price": float(stop_px),
                                    "qty": int(qty),
                                },
                            },
                        }
                        structured["trade_plan"] = full_plan
                        structured["plan_hash"] = plan_hash
                        record_system_event(
                            db,
                            level="INFO",
                            category="AI_ORCH",
                            message="Trade plan proposed.",
                            correlation_id=corr,
                            details={"event_type": "PLAN_PROPOSED", "plan_id": plan.plan_id},
                        )
                    else:
                        args = tc.arguments or {}
                        plan_id = str(args.get("plan_id") or "").strip()
                        if not plan_id:
                            raise ValueError("plan_id required")
                        plan = get_trade_plan(db, plan_id=plan_id)
                        if plan is None:
                            raise ValueError("plan not found")

                        if not authorization_message_id:
                            raise ValueError("authorization_message_id missing")

                        if not _is_explicit_execute(user_message):
                            out = {"executed": False, "veto": True, "reason": "USER_NOT_EXPLICIT"}
                        elif (
                            not tm_cfg.feature_flags.ai_execution_enabled
                            or tm_cfg.kill_switch.ai_execution_kill_switch
                        ):
                            out = {"executed": False, "veto": True, "reason": "EXECUTION_DISABLED"}
                        elif is_execution_hard_disabled(tm_cfg):
                            out = {"executed": False, "veto": True, "reason": "EXECUTION_KILL_SWITCH"}
                        elif str(tm_cfg.kite_mcp.last_status or "").lower() != "connected":
                            out = {"executed": False, "veto": True, "reason": "MCP_NOT_CONNECTED"}
                        else:
                            # Playbook pre-trade decision (passive by default; enabled=false).
                            shadow = None
                            try:
                                sym0 = str((plan.intent.symbols or [""])[0] or "").strip().upper()
                                prod0 = str(plan.intent.product or "CNC").strip().upper()
                                if sym0:
                                    shadow = (
                                        db.execute(
                                            select(AiTmPositionShadow)
                                            .where(
                                                AiTmPositionShadow.broker_account_id == account_id,
                                                AiTmPositionShadow.symbol == sym0,
                                                AiTmPositionShadow.product == prod0,
                                                AiTmPositionShadow.status == "OPEN",
                                            )
                                            .order_by(desc(AiTmPositionShadow.last_seen_at))
                                            .limit(1)
                                        )
                                        .scalars()
                                        .first()
                                    )
                            except Exception:
                                shadow = None

                            intent_type = (
                                "ADD"
                                if (shadow is not None and float(shadow.qty_current or 0.0) > 0)
                                else "ENTRY"
                            )
                            pb_dec = evaluate_playbook_pretrade(
                                db,
                                shadow=shadow,
                                intent=IntentContext(
                                    intent_type=intent_type,
                                    source="AI_ASSISTANT",
                                    symbol=str((plan.intent.symbols or [""])[0] or "").strip().upper(),
                                    product=str(plan.intent.product or "CNC").strip().upper(),
                                    qty=float((plan.intent.constraints or {}).get("qty") or 0.0)
                                    if isinstance(plan.intent.constraints, dict)
                                    else None,
                                ),
                            )
                            structured["playbook_pretrade"] = pb_dec.model_dump(mode="json")
                            record_system_event(
                                db,
                                level="INFO",
                                category="AI_ORCH",
                                message="Playbook pre-trade evaluated.",
                                correlation_id=corr,
                                details={
                                    "event_type": "PLAYBOOK_PRETRADE",
                                    "decision": pb_dec.decision.value,
                                    "symbol": str((plan.intent.symbols or [""])[0] or ""),
                                    "product": str(plan.intent.product or ""),
                                },
                            )
                            if pb_dec.decision.value == "BLOCK":
                                out = {
                                    "executed": False,
                                    "veto": True,
                                    "reason": "PLAYBOOK_BLOCKED",
                                    "playbook": pb_dec.model_dump(mode="json"),
                                }
                            else:
                                # Apply safe deterministic adjustments (e.g., qty) before RiskGate.
                                if pb_dec.decision.value == "ADJUST":
                                    adj_qty = (
                                        pb_dec.adjustments.get("qty")
                                        if isinstance(pb_dec.adjustments, dict)
                                        else None
                                    )
                                    if adj_qty is not None and isinstance(plan.intent.constraints, dict):
                                        try:
                                            q = float(adj_qty)
                                            if q > 0:
                                                new_constraints = dict(plan.intent.constraints or {})
                                                new_constraints["qty"] = int(q) if float(q).is_integer() else float(q)
                                                plan = plan.model_copy(
                                                    update={
                                                        "intent": plan.intent.model_copy(
                                                            update={"constraints": new_constraints}
                                                        )
                                                    }
                                                )
                                        except Exception:
                                            pass

                            if pb_dec.decision.value != "BLOCK":
                                # Build broker snapshot + quotes cache from DB for RiskGate.
                                broker_snap = await fetch_kite_mcp_snapshot(db, settings, account_id=account_id)
                                qrows: list[Quote] = []
                                now = datetime.now(UTC)
                                for sym in plan.intent.symbols:
                                    px = _latest_close(str(sym).upper())
                                    if px is not None:
                                        qrows.append(
                                            Quote(symbol=str(sym).upper(), last_price=float(px), as_of_ts=now)
                                        )
                                broker_snap = broker_snap.model_copy(update={"quotes_cache": qrows})
                                ledger_snapshot = build_ledger_snapshot(db, account_id=account_id)

                                risk = evaluate_riskgate(
                                    plan=plan,
                                    broker=broker_snap,
                                    ledger=ledger_snapshot,
                                    eval_ts=broker_snap.as_of_ts,
                                ).decision
                                trace.riskgate_result = risk
                                structured["riskgate"] = risk.model_dump(mode="json")
                                if risk.outcome.value != "allow":
                                    out = {
                                        "executed": False,
                                        "veto": True,
                                        "reason": "RISK_DENY",
                                        "risk": risk.model_dump(mode="json"),
                                    }
                                    record_system_event(
                                        db,
                                        level="WARNING",
                                        category="AI_ORCH",
                                        message="RiskGate denied execution.",
                                        correlation_id=corr,
                                        details={"event_type": "RISK_CHECK_DENIED", "policy_hash": risk.policy_hash},
                                    )
                                else:
                                    record_system_event(
                                        db,
                                        level="INFO",
                                        category="AI_ORCH",
                                        message="RiskGate passed.",
                                        correlation_id=corr,
                                        details={"event_type": "RISK_CHECK_PASSED", "policy_hash": risk.policy_hash},
                                    )
                                    plan_hash = _hash_payload(plan.model_dump(mode="json"))
                                    idem_key = _hash_payload(
                                        {
                                            "authorization_message_id": authorization_message_id,
                                            "plan_hash": plan_hash,
                                            "broker": "kite_mcp",
                                            "account_id": account_id,
                                        }
                                    )

                                    trade_client = KiteMcpTradeClient(session=session)

                                    class _Broker:
                                        name = "kite_mcp"

                                        def __init__(self, tc: KiteMcpTradeClient) -> None:
                                            self._tc = tc

                                        async def place_order(self, *, account_id: str, intent: Any):
                                            return await self._tc.place_order(account_id=account_id, intent=intent)

                                        async def get_orders(self, *, account_id: str):
                                            _ = account_id
                                            return await self._tc.get_orders()

                                    engine = ExecutionEngine()
                                    exec_res = await engine.execute_to_broker_async(
                                        db,
                                        user_id=None,
                                        account_id=account_id,
                                        correlation_id=corr,
                                        plan=plan,
                                        idempotency_key=idem_key,
                                        broker=_Broker(trade_client),
                                    )
                                    # Post-trade reconcile.
                                    rec = await post_trade_reconcile(
                                        db, settings, account_id=account_id, user_id=None
                                    )
                                    # Mark idempotency as reconciled.
                                    rec_id = int(exec_res.get("idempotency_record_id") or 0)
                                    if rec_id:
                                        IdempotencyStore().mark_status(
                                            db,
                                            record_id=rec_id,
                                            status=IdempotencyStore.STATUS_RECONCILED,
                                            result_patch={"reconciliation": rec},
                                        )
                                    out = {
                                        "executed": True,
                                        "execution": exec_res,
                                        "reconciliation": rec,
                                        "idempotency_key": idem_key,
                                    }
                                    structured["execution"] = out

                        # Always persist the execution evaluation for trace/UI.
                        if "execution" not in structured:
                            structured["execution"] = out

                        record_system_event(
                            db,
                            level="INFO",
                            category="AI_ORCH",
                            message="AI trade execution evaluated.",
                            correlation_id=corr,
                            details={"event_type": "AI_EXECUTION_EVALUATED", "plan_id": plan_id},
                        )

                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    safe_args = redact_for_llm(tc.arguments or {})
                    meta = persist_operator_payload(
                        db,
                        decision_id=trace.decision_id,
                        tool_name=tc.name,
                        tool_call_id=tc.tool_call_id,
                        account_id=account_id,
                        user_id=None,
                        payload=out,
                    )
                    try:
                        llm_summary = summarize_tool_for_llm(settings, tool_name=tc.name, operator_payload=out)
                    except SafeSummaryError:
                        llm_summary = {"schema": "tool_error.v1", "tool": tc.name, "isError": True}
                    preview = tool_result_preview(llm_summary)
                    tool_logs.append(
                        ToolCallLog(
                            name=tc.name,
                            arguments=safe_args,
                            status="ok",
                            duration_ms=duration_ms,
                            result_preview=preview,
                        )
                    )
                    if event_cb is not None:
                        try:
                            await event_cb(
                                {
                                    "type": "tool_call",
                                    "name": tc.name,
                                    "arguments": safe_args,
                                    "status": "ok",
                                    "duration_ms": duration_ms,
                                    "result_preview": preview,
                                }
                            )
                        except Exception:
                            pass
                    trace.tools_called.append(
                        DecisionToolCall(
                            tool_name=tc.name,
                            input_summary={"arguments": safe_args},
                            output_summary={"preview": preview},
                            duration_ms=duration_ms,
                            operator_payload_meta=meta,
                            llm_summary=llm_summary,
                            broker_raw_count=int(meta.get("items_count") or 0),
                            llm_summary_count=_llm_summary_count(llm_summary),
                        )
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.tool_call_id,
                            "content": json.dumps(
                                llm_summary,
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                                default=str,
                            ),
                        }
                    )
                    continue
                except Exception as exc:
                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    out_err = {"isError": True, "error": str(exc) or "internal tool failed", "tool": tc.name}
                    safe_args = redact_for_llm(tc.arguments or {})
                    meta = persist_operator_payload(
                        db,
                        decision_id=trace.decision_id,
                        tool_name=tc.name,
                        tool_call_id=tc.tool_call_id,
                        account_id=account_id,
                        user_id=None,
                        payload=out_err,
                    )
                    llm_summary = {"schema": "tool_error.v1", "tool": tc.name, "isError": True, "error": str(exc) or ""}
                    preview = tool_result_preview(llm_summary)
                    tool_logs.append(
                        ToolCallLog(
                            name=tc.name,
                            arguments=safe_args,
                            status="error",
                            duration_ms=duration_ms,
                            result_preview=preview,
                            error=str(exc) or "internal tool failed",
                        )
                    )
                    if event_cb is not None:
                        try:
                            await event_cb(
                                {
                                    "type": "tool_call",
                                    "name": tc.name,
                                    "arguments": safe_args,
                                    "status": "error",
                                    "duration_ms": duration_ms,
                                    "result_preview": preview,
                                    "error": str(exc) or "internal tool failed",
                                }
                            )
                        except Exception:
                            pass
                    trace.tools_called.append(
                        DecisionToolCall(
                            tool_name=tc.name,
                            input_summary={"arguments": safe_args},
                            output_summary={"status": "error", "error": str(exc) or "internal tool failed"},
                            duration_ms=duration_ms,
                            operator_payload_meta=meta,
                            llm_summary=llm_summary,
                            broker_raw_count=int(meta.get("items_count") or 0),
                            llm_summary_count=_llm_summary_count(llm_summary),
                        )
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.tool_call_id,
                            "content": json.dumps(
                                llm_summary,
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                                default=str,
                            ),
                        }
                    )
                    continue

            meta = tools_by_name.get(tc.name)
            pol = evaluate_tool_policy(
                tool_name=tc.name,
                tool_meta=meta,
                user_message=user_message,
                ai_execution_enabled=bool(tm_cfg.feature_flags.ai_execution_enabled),
            )
            if not pol.allowed:
                out = {"isError": True, "blocked": True, "reason": pol.reason, "tool": tc.name}
                duration_ms = int((time.perf_counter() - t0) * 1000)
                safe_args = redact_for_llm(tc.arguments or {})
                meta2 = persist_operator_payload(
                    db,
                    decision_id=trace.decision_id,
                    tool_name=tc.name,
                    tool_call_id=tc.tool_call_id,
                    account_id=account_id,
                    user_id=None,
                    payload=out,
                )
                llm_summary2: dict[str, Any] = dict(out)
                preview2 = tool_result_preview(llm_summary2)
                tool_logs.append(
                    ToolCallLog(
                        name=tc.name,
                        arguments=safe_args,
                        status="blocked",
                        duration_ms=duration_ms,
                        result_preview=preview2,
                        error=pol.reason,
                    )
                )
                if event_cb is not None:
                    try:
                        await event_cb(
                            {
                                "type": "tool_call",
                                "name": tc.name,
                                "arguments": safe_args,
                                "status": "blocked",
                                "duration_ms": duration_ms,
                                "result_preview": preview2,
                                "error": pol.reason,
                            }
                        )
                    except Exception:
                        pass
                trace.tools_called.append(
                    DecisionToolCall(
                        tool_name=tc.name,
                        input_summary={"arguments": safe_args},
                        output_summary={"blocked": True, "reason": pol.reason},
                        duration_ms=duration_ms,
                        operator_payload_meta=meta2,
                        llm_summary=llm_summary2,
                        broker_raw_count=int(meta2.get("items_count") or 0),
                        llm_summary_count=_llm_summary_count(llm_summary2),
                    )
                )
                record_system_event(
                    db,
                    level="WARNING",
                    category="AI_ORCH",
                    message="AI tool blocked.",
                    correlation_id=corr,
                    details={"event_type": "AI_TOOL_BLOCKED", "tool": tc.name, "reason": pol.reason},
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "content": json.dumps(
                            llm_summary2,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                            default=str,
                        ),
                    }
                )
                continue

            # PII safety: do not execute tools for remote LLMs unless we have a deterministic safe summary.
            if is_remote_provider and not tool_has_safe_summary(tc.name):
                out_ns = {
                    "isError": True,
                    "blocked": True,
                    "reason": "NO_SAFE_SUMMARY_REGISTERED",
                    "tool": tc.name,
                }
                duration_ms = int((time.perf_counter() - t0) * 1000)
                safe_args = redact_for_llm(tc.arguments or {})
                meta_ns = persist_operator_payload(
                    db,
                    decision_id=trace.decision_id,
                    tool_name=tc.name,
                    tool_call_id=tc.tool_call_id,
                    account_id=account_id,
                    user_id=None,
                    payload=out_ns,
                )
                preview_ns = tool_result_preview(out_ns)
                tool_logs.append(
                    ToolCallLog(
                        name=tc.name,
                        arguments=safe_args,
                        status="blocked",
                        duration_ms=duration_ms,
                        result_preview=preview_ns,
                        error="no safe summary registered",
                    )
                )
                trace.tools_called.append(
                    DecisionToolCall(
                        tool_name=tc.name,
                        input_summary={"arguments": safe_args},
                        output_summary={"blocked": True, "reason": "NO_SAFE_SUMMARY_REGISTERED"},
                        duration_ms=duration_ms,
                        operator_payload_meta=meta_ns,
                        llm_summary=out_ns,
                        broker_raw_count=int(meta_ns.get("items_count") or 0),
                        llm_summary_count=_llm_summary_count(out_ns),
                        truncation_reason="blocked_no_safe_summary",
                    )
                )
                record_system_event(
                    db,
                    level="WARNING",
                    category="AI_ORCH",
                    message="AI tool blocked (no safe summary).",
                    correlation_id=corr,
                    details={
                        "event_type": "AI_TOOL_BLOCKED",
                        "tool": tc.name,
                        "reason": "NO_SAFE_SUMMARY_REGISTERED",
                    },
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "content": json.dumps(
                            out_ns,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                            default=str,
                        ),
                    }
                )
                continue

            try:
                res = await asyncio.wait_for(
                    session.tools_call(name=tc.name, arguments=tc.arguments or {}),
                    timeout=10,
                )
                status_s = "ok" if not (isinstance(res, dict) and res.get("isError") is True) else "error"
                err = None
                if status_s == "error":
                    err = str(((res.get("content") or [{}])[0] or {}).get("text") or "tool error")
                duration_ms = int((time.perf_counter() - t0) * 1000)
                safe_args = redact_for_llm(tc.arguments or {})
                operator_payload = _extract_tool_json(res) if isinstance(res, dict) else res
                meta3 = persist_operator_payload(
                    db,
                    decision_id=trace.decision_id,
                    tool_name=tc.name,
                    tool_call_id=tc.tool_call_id,
                    account_id=account_id,
                    user_id=None,
                    payload=operator_payload,
                )
                if status_s == "ok":
                    try:
                        llm_summary3 = summarize_tool_for_llm(
                            settings,
                            tool_name=tc.name,
                            operator_payload=operator_payload,
                        )
                    except SafeSummaryError as exc:
                        # Fail closed for remote providers: do not proceed if we cannot safely summarize.
                        pii_abort_message = (
                            f"Blocked sending broker data to remote LLM: no safe summary for tool '{tc.name}'. "
                            f"({str(exc) or 'missing summarizer'})"
                        )
                        final_text = pii_abort_message
                        trace.final_outcome = {
                            "assistant_message": final_text,
                            "blocked_by": "PII_POLICY",
                            "reason": "NO_SAFE_SUMMARY",
                            "tool": tc.name,
                        }
                        trace.explanations = ["PII_POLICY_NO_SAFE_SUMMARY"]
                        record_system_event(
                            db,
                            level="WARNING",
                            category="AI_ORCH",
                            message="Tool result blocked (no safe summary).",
                            correlation_id=corr,
                            details={"event_type": "AI_PII_BLOCKED", "tool": tc.name},
                        )
                        break
                else:
                    llm_summary3 = {"schema": "tool_error.v1", "tool": tc.name, "isError": True, "error": err or ""}
                preview = tool_result_preview(llm_summary3)
                tool_logs.append(
                    ToolCallLog(
                        name=tc.name,
                        arguments=safe_args,
                        status=status_s,
                        duration_ms=duration_ms,
                        result_preview=preview,
                        error=err,
                    )
                )
                if event_cb is not None:
                    try:
                        await event_cb(
                            {
                                "type": "tool_call",
                                "name": tc.name,
                                "arguments": safe_args,
                                "status": status_s,
                                "duration_ms": duration_ms,
                                "result_preview": preview,
                                "error": err,
                            }
                        )
                    except Exception:
                        pass
                trace.tools_called.append(
                    DecisionToolCall(
                        tool_name=tc.name,
                        input_summary={"arguments": safe_args},
                        output_summary={"status": status_s, "preview": preview},
                        duration_ms=duration_ms,
                        operator_payload_meta=meta3,
                        llm_summary=llm_summary3,
                        broker_raw_count=int(meta3.get("items_count") or 0),
                        llm_summary_count=_llm_summary_count(llm_summary3),
                    )
                )
                record_system_event(
                    db,
                    level="INFO" if status_s == "ok" else "WARNING",
                    category="AI_ORCH",
                    message="AI tool called.",
                    correlation_id=corr,
                    details={
                        "event_type": "AI_TOOL_CALLED",
                        "tool": tc.name,
                        "status": status_s,
                        "duration_ms": duration_ms,
                    },
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "content": json.dumps(
                            llm_summary3,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                            default=str,
                        ),
                    }
                )
            except Exception as exc:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                out = {"isError": True, "error": str(exc) or "tool call failed", "tool": tc.name}
                safe_args = redact_for_llm(tc.arguments or {})
                meta4 = persist_operator_payload(
                    db,
                    decision_id=trace.decision_id,
                    tool_name=tc.name,
                    tool_call_id=tc.tool_call_id,
                    account_id=account_id,
                    user_id=None,
                    payload=out,
                )
                llm_summary4 = {"schema": "tool_error.v1", "tool": tc.name, "isError": True, "error": str(exc) or ""}
                preview = tool_result_preview(llm_summary4)
                tool_logs.append(
                    ToolCallLog(
                        name=tc.name,
                        arguments=safe_args,
                        status="error",
                        duration_ms=duration_ms,
                        result_preview=preview,
                        error=str(exc) or "tool call failed",
                    )
                )
                if event_cb is not None:
                    try:
                        await event_cb(
                            {
                                "type": "tool_call",
                                "name": tc.name,
                                "arguments": safe_args,
                                "status": "error",
                                "duration_ms": duration_ms,
                                "result_preview": preview,
                                "error": str(exc) or "tool call failed",
                            }
                        )
                    except Exception:
                        pass
                trace.tools_called.append(
                    DecisionToolCall(
                        tool_name=tc.name,
                        input_summary={"arguments": safe_args},
                        output_summary={"status": "error", "error": str(exc) or "tool call failed"},
                        duration_ms=duration_ms,
                        operator_payload_meta=meta4,
                        llm_summary=llm_summary4,
                        broker_raw_count=int(meta4.get("items_count") or 0),
                        llm_summary_count=_llm_summary_count(llm_summary4),
                    )
                )
                record_system_event(
                    db,
                    level="WARNING",
                    category="AI_ORCH",
                    message="AI tool call failed.",
                    correlation_id=corr,
                    details={"event_type": "AI_TOOL_ERROR", "tool": tc.name, "error": str(exc) or "unknown"},
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "content": json.dumps(
                            llm_summary4,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                            default=str,
                        ),
                    }
                )
        if pii_abort_message:
            break

    if not final_text:
        final_text = "I couldn't complete that request right now."

    if event_cb is not None and stream_assistant:
        try:
            chunk_size = 80
            for i in range(0, len(final_text), chunk_size):
                await event_cb({"type": "assistant_delta", "text": final_text[i : i + chunk_size]})
        except Exception:
            pass

    prior = trace.final_outcome if isinstance(trace.final_outcome, dict) else {}
    trace.final_outcome = {
        **prior,
        "assistant_message": final_text,
        "tool_calls": [t.__dict__ for t in tool_logs],
        **structured,
    }
    trace.explanations = []

    # Persist trace.
    audit_store.persist_decision_trace(db, trace, user_id=None)

    record_system_event(
        db,
        level="INFO",
        category="AI_ORCH",
        message="AI response returned.",
        correlation_id=corr,
        details={"event_type": "AI_RESPONSE_RETURNED", "decision_id": trace.decision_id, "tool_calls": len(tool_logs)},
    )

    return ChatResult(assistant_message=final_text, decision_id=trace.decision_id, tool_calls=tool_logs)


__all__ = ["ChatResult", "ToolCallLog", "run_chat"]
