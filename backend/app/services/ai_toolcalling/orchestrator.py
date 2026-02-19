from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.ai_trading_manager import DecisionToolCall
from app.services.ai.active_config import get_active_config
from app.services.ai.provider_keys import decrypt_key_value, get_key
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source
from app.services.ai_trading_manager.feature_flags import require_ai_assistant_enabled
from app.services.kite_mcp.secrets import get_auth_session_id
from app.services.kite_mcp.session_manager import kite_mcp_sessions
from app.services.system_events import record_system_event

from .mcp_tools import tool_result_preview
from .openai_toolcaller import OpenAiChatError, openai_chat_with_tools
from .policy import evaluate_tool_policy, tool_lookup_map
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
    openai_tools = cached.openai_tools
    tools_hash = cached.tools_hash
    tools_by_name = tool_lookup_map(cached.mcp_tools)

    if refreshed:
        record_system_event(
            db,
            level="INFO",
            category="AI_ORCH",
            message="AI tool list refreshed.",
            correlation_id=corr,
            details={"event_type": "AI_TOOL_LIST_REFRESHED", "tools_hash": tools_hash, "count": len(cached.mcp_tools)},
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
            **_safe_prompt_audit(user_message, do_not_send_pii=bool(ai_cfg.do_not_send_pii)),
        },
    )

    system_prompt = (
        "You are SigmaTrader's AI Trading Manager. "
        "You can call tools to read broker-truth portfolio data via Kite MCP. "
        "Only call tools that help answer the user's question. "
        "Do not place/modify/cancel orders; if asked, explain that execution is policy-gated and may be vetoed.\n\n"
        "When you answer, be concise and structured with short sections."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    if ui_context:
        messages.append({"role": "system", "content": f"UI context (json): {redact_for_llm(ui_context)}"})
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
        },
    )

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
