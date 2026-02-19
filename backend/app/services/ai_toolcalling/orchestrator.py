from __future__ import annotations

import json
import re
import asyncio
import hashlib
from datetime import UTC, datetime
import time
from dataclasses import dataclass
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Candle
from app.schemas.ai_trading_manager import DecisionToolCall, Quote, TradeIntent
from app.services.ai.active_config import get_active_config
from app.services.ai.provider_keys import decrypt_key_value, get_key
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source
from app.services.ai_trading_manager.ai_settings_config import is_execution_hard_disabled
from app.services.ai_trading_manager.execution.engine import ExecutionEngine
from app.services.ai_trading_manager.execution.idempotency_store import IdempotencyStore
from app.services.ai_trading_manager.execution.post_trade_reconcile import post_trade_reconcile
from app.services.ai_trading_manager.feature_flags import require_ai_assistant_enabled
from app.services.ai_trading_manager.ledger_snapshot import build_ledger_snapshot
from app.services.ai_trading_manager.plan_engine import new_plan_from_intent, normalize_trade_plan
from app.services.ai_trading_manager.playbooks import get_trade_plan, upsert_trade_plan
from app.services.ai_trading_manager.riskgate.engine import evaluate_riskgate
from app.services.ai_trading_manager.sizing import extract_equity_value, suggest_qty
from app.services.kite_mcp.secrets import get_auth_session_id
from app.services.kite_mcp.session_manager import kite_mcp_sessions
from app.services.kite_mcp.snapshot import fetch_kite_mcp_snapshot
from app.services.kite_mcp.trade import KiteMcpTradeClient
from app.services.system_events import record_system_event

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
) -> ChatResult:
    require_ai_assistant_enabled(db, settings)
    corr = correlation_id or _corr()

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

    openai_tools = mcp_tools_to_openai_tools(safe_mcp_tools) + internal_tools
    tools_hash = hash_tool_definitions(openai_tools)
    tools_by_name = tool_lookup_map(safe_mcp_tools)

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
                "safe_count": len(safe_mcp_tools),
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
        "For trading intents, first call propose_trade_plan. "
        "Only call execute_trade_plan when the user explicitly asks to execute.\n\n"
        "Never call broker order tools directly. Execution is policy-gated and may be vetoed.\n\n"
        "When you answer, be concise and structured with short sections."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    if ui_context:
        messages.append({"role": "system", "content": f"UI context (json): {redact_for_llm(ui_context)}"})
    if attachments:
        messages.append({"role": "system", "content": f"Attachments (summaries json): {redact_for_llm(attachments)}"})
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

    final_text = ""
    max_iters = 6
    for _i in range(max_iters):
        try:
            turn = await openai_chat_with_tools(
                api_key=api_key,
                model=str(ai_cfg.model),
                messages=messages,
                tools=openai_tools,
                timeout_seconds=30,
                max_tokens=ai_cfg.limits.max_tokens_per_request,
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
                            "arguments": tool_result_preview(redact_for_llm(tc.arguments or {}), max_chars=4000),
                        },
                    }
                    for tc in turn.tool_calls
                ],
            }
        )

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
                            # Build broker snapshot + quotes cache from DB for RiskGate.
                            broker_snap = await fetch_kite_mcp_snapshot(db, settings, account_id=account_id)
                            qrows: list[Quote] = []
                            now = datetime.now(UTC)
                            for sym in plan.intent.symbols:
                                px = _latest_close(str(sym).upper())
                                if px is not None:
                                    qrows.append(Quote(symbol=str(sym).upper(), last_price=float(px), as_of_ts=now))
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
                                rec = await post_trade_reconcile(db, settings, account_id=account_id, user_id=None)
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
                    preview = tool_result_preview(redact_for_llm(out))
                    tool_logs.append(
                        ToolCallLog(
                            name=tc.name,
                            arguments=safe_args,
                            status="ok",
                            duration_ms=duration_ms,
                            result_preview=preview,
                        )
                    )
                    trace.tools_called.append(
                        DecisionToolCall(
                            tool_name=tc.name,
                            input_summary={"arguments": safe_args},
                            output_summary={"preview": preview},
                            duration_ms=duration_ms,
                        )
                    )
                    messages.append({"role": "tool", "tool_call_id": tc.tool_call_id, "content": preview})
                    continue
                except Exception as exc:
                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    out_err = {"isError": True, "error": str(exc) or "internal tool failed", "tool": tc.name}
                    safe_args = redact_for_llm(tc.arguments or {})
                    preview = tool_result_preview(redact_for_llm(out_err))
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
                    trace.tools_called.append(
                        DecisionToolCall(
                            tool_name=tc.name,
                            input_summary={"arguments": safe_args},
                            output_summary={"status": "error", "error": str(exc) or "internal tool failed"},
                            duration_ms=duration_ms,
                        )
                    )
                    messages.append({"role": "tool", "tool_call_id": tc.tool_call_id, "content": preview})
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
                tool_logs.append(
                    ToolCallLog(
                        name=tc.name,
                        arguments=safe_args,
                        status="blocked",
                        duration_ms=duration_ms,
                        result_preview=tool_result_preview(redact_for_llm(out)),
                        error=pol.reason,
                    )
                )
                trace.tools_called.append(
                    DecisionToolCall(
                        tool_name=tc.name,
                        input_summary={"arguments": safe_args},
                        output_summary={"blocked": True, "reason": pol.reason},
                        duration_ms=duration_ms,
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
                        "content": tool_result_preview(redact_for_llm(out)),
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
                safe_res = redact_for_llm(res)
                preview = tool_result_preview(safe_res)
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
                trace.tools_called.append(
                    DecisionToolCall(
                        tool_name=tc.name,
                        input_summary={"arguments": safe_args},
                        output_summary={"status": status_s, "preview": preview},
                        duration_ms=duration_ms,
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
                messages.append({"role": "tool", "tool_call_id": tc.tool_call_id, "content": preview})
            except Exception as exc:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                out = {"isError": True, "error": str(exc) or "tool call failed", "tool": tc.name}
                safe_args = redact_for_llm(tc.arguments or {})
                preview = tool_result_preview(redact_for_llm(out))
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
                trace.tools_called.append(
                    DecisionToolCall(
                        tool_name=tc.name,
                        input_summary={"arguments": safe_args},
                        output_summary={"status": "error", "error": str(exc) or "tool call failed"},
                        duration_ms=duration_ms,
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
                messages.append({"role": "tool", "tool_call_id": tc.tool_call_id, "content": preview})

    if not final_text:
        final_text = "I couldn't complete that request right now."

    trace.final_outcome = {
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
