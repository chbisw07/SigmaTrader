from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.ai_settings import AiSettings
from app.services.ai_trading_manager.operator_payload_store import persist_operator_payload
from app.services.system_events import record_system_event

from .lsg_policy import LsgPolicyDecision, capability_for_tool, evaluate_lsg_policy
from .lsg_sanitizer import sanitize_digest_payload, sanitize_kite_payload
from .lsg_types import (
    ToolCapability,
    ToolRequestEnvelope,
    ToolRequestSource,
    ToolResultEnvelope,
    ToolSanitizationMeta,
)


@dataclass(frozen=True)
class LsgContext:
    db: Session
    settings: Settings
    tm_cfg: AiSettings
    decision_id: str
    correlation_id: str
    account_id: str = "default"
    user_id: int | None = None


@dataclass(frozen=True)
class LsgExecution:
    policy: LsgPolicyDecision
    duration_ms: int
    raw_payload: Any
    result: ToolResultEnvelope


class _WindowRateLimiter:
    """Simple in-memory sliding window limiter (best-effort).

    This is intentionally conservative and process-local.
    """

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def allow(self, *, key: str, max_per_minute: int) -> bool:
        if max_per_minute <= 0:
            return False
        now = time.time()
        window_start = now - 60.0
        arr = self._hits.get(key) or []
        arr = [t for t in arr if t >= window_start]
        if len(arr) >= max_per_minute:
            self._hits[key] = arr
            return False
        arr.append(now)
        self._hits[key] = arr
        return True


_RL = _WindowRateLimiter()


def _coerce_args(value: Any) -> dict[str, Any] | None:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return None


def _schema_type_ok(expected: str, v: Any) -> bool:
    t = (expected or "").strip().lower()
    if t == "string":
        return isinstance(v, str)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "array":
        return isinstance(v, list)
    if t == "object":
        return isinstance(v, dict)
    return True


def validate_args_against_schema(*, schema: dict[str, Any] | None, args: dict[str, Any], strict: bool) -> str | None:
    """Best-effort JSON-schema-like validator (enough for safety-gating).

    Returns None if valid, or an error string if invalid.
    """
    if schema is None or not isinstance(schema, dict):
        return None if not strict else "Missing tool input schema."
    t = str(schema.get("type") or "object").lower()
    if t != "object":
        # We only accept object args in this system.
        return "Tool args must be a JSON object."
    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    required = schema.get("required")
    req = required if isinstance(required, list) else []
    for k in req:
        ks = str(k)
        if ks and ks not in args:
            return f"Missing required arg: {ks}"
    if strict:
        for k in args.keys():
            if k not in props:
                return f"Unknown arg key: {k}"
    for k, spec in props.items():
        if k not in args:
            continue
        if not isinstance(spec, dict):
            continue
        v = args.get(k)
        expected_type = str(spec.get("type") or "").strip()
        if expected_type and not _schema_type_ok(expected_type, v):
            return f"Invalid type for {k}: expected {expected_type}"
        enum = spec.get("enum")
        if isinstance(enum, list) and enum and v is not None:
            if v not in enum:
                return f"Invalid value for {k}: expected one of {enum}"
        if expected_type == "array" and isinstance(v, list):
            items = spec.get("items")
            if isinstance(items, dict) and items.get("type"):
                it = str(items.get("type") or "")
                for i, row in enumerate(v):
                    if not _schema_type_ok(it, row):
                        return f"Invalid item type for {k}[{i}]: expected {it}"
    return None


def _rate_limits_for_tool(tm_cfg: AiSettings, tool_name: str) -> tuple[int | None, int | None]:
    # Defaults are conservative; can be overridden by settings.hybrid_llm.rate_limits.
    defaults: dict[str, tuple[int, int]] = {
        "search_instruments": (30, 0),
        "get_ltp": (90, 45),
        "get_quotes": (60, 30),
        "get_ohlc": (30, 15),
        "get_historical_data": (20, 10),
    }
    t = (tool_name or "").strip()
    per_min, per_sym = defaults.get(t, (0, 0))

    try:
        custom = getattr(getattr(tm_cfg, "hybrid_llm", None), "rate_limits", None)
        if isinstance(custom, dict) and isinstance(custom.get(t), dict):
            cfg = custom.get(t) or {}
            if cfg.get("per_minute") is not None:
                per_min = int(cfg.get("per_minute") or 0)
            if cfg.get("per_symbol_per_minute") is not None:
                per_sym = int(cfg.get("per_symbol_per_minute") or 0)
    except Exception:
        pass

    return (per_min if per_min > 0 else None, per_sym if per_sym > 0 else None)


def _extract_symbol_key(args: dict[str, Any]) -> str | None:
    # Heuristic: try common arg names. This is best-effort.
    for k in ("symbol", "tradingsymbol", "scrip", "instrument", "instrument_key"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    for k in ("symbols", "tradingsymbols", "instruments"):
        v = args.get(k)
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str) and first.strip():
                return first.strip().upper()
    return None


def build_tool_request(
    *,
    request_id: str,
    source: ToolRequestSource,
    mode: str,
    tool_name: str,
    args: dict[str, Any] | None,
    reason: str | None = None,
    risk_tier: str | None = None,
) -> ToolRequestEnvelope:
    cap = capability_for_tool(tool_name)
    return ToolRequestEnvelope(
        request_id=request_id,
        source=source,
        mode=mode,
        capability=cap,
        tool_name=str(tool_name),
        args=args or {},
        reason=reason,
        risk_tier=risk_tier,
    )


async def lsg_execute(
    ctx: LsgContext,
    *,
    request: ToolRequestEnvelope,
    tool_input_schema: dict[str, Any] | None,
    executor: Callable[[dict[str, Any]], Awaitable[Any]],
    bucket_numbers: bool = False,
) -> LsgExecution:
    t0 = time.perf_counter()

    # Capability is derived (untrusted input); rewrite to computed value.
    computed_cap = capability_for_tool(request.tool_name)
    req2 = request.model_copy(update={"capability": computed_cap})

    pol = evaluate_lsg_policy(source=req2.source, tool_name=req2.tool_name, tm_cfg=ctx.tm_cfg)
    if not pol.allowed:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        denied = ToolResultEnvelope(
            request_id=req2.request_id,
            status="denied",
            denial_reason=str(pol.denial_reason or "policy"),
            data=None,
            sanitization=ToolSanitizationMeta(),
            audit_ref=None,
        )
        meta = persist_operator_payload(
            ctx.db,
            decision_id=ctx.decision_id,
            tool_name=f"lsg.{req2.tool_name}",
            tool_call_id=req2.request_id,
            account_id=ctx.account_id,
            user_id=ctx.user_id,
            payload={
                "request": req2.model_dump(mode="json"),
                "result": denied.model_dump(mode="json"),
                "policy_reason": pol.reason,
            },
        )
        denied = denied.model_copy(update={"audit_ref": str(meta.get("payload_id") or "")})
        record_system_event(
            ctx.db,
            level="WARNING",
            category="AI_LSG",
            message="LSG denied tool request.",
            correlation_id=ctx.correlation_id,
            details={
                "request_id": req2.request_id,
                "tool": req2.tool_name,
                "source": req2.source,
                "capability": computed_cap.value,
                "denial_reason": str(pol.denial_reason or "policy"),
                "policy_reason": pol.reason,
                "audit_ref": denied.audit_ref,
            },
        )
        return LsgExecution(policy=pol, duration_ms=duration_ms, raw_payload=None, result=denied)

    strict = req2.source == "remote"
    args = _coerce_args(req2.args)
    if args is None:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        out = ToolResultEnvelope(
            request_id=req2.request_id,
            status="denied",
            denial_reason="invalid_args",
            data=None,
            sanitization=ToolSanitizationMeta(),
        )
        meta = persist_operator_payload(
            ctx.db,
            decision_id=ctx.decision_id,
            tool_name=f"lsg.{req2.tool_name}",
            tool_call_id=req2.request_id,
            account_id=ctx.account_id,
            user_id=ctx.user_id,
            payload={"request": req2.model_dump(mode="json"), "error": "args_not_object"},
        )
        out = out.model_copy(update={"audit_ref": str(meta.get("payload_id") or "")})
        return LsgExecution(policy=pol, duration_ms=duration_ms, raw_payload=None, result=out)

    err = validate_args_against_schema(schema=tool_input_schema, args=args, strict=strict)
    if err:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        out = ToolResultEnvelope(
            request_id=req2.request_id,
            status="denied",
            denial_reason="invalid_args",
            data={"error": err},
            sanitization=ToolSanitizationMeta(),
        )
        meta = persist_operator_payload(
            ctx.db,
            decision_id=ctx.decision_id,
            tool_name=f"lsg.{req2.tool_name}",
            tool_call_id=req2.request_id,
            account_id=ctx.account_id,
            user_id=ctx.user_id,
            payload={"request": req2.model_dump(mode="json"), "error": err},
        )
        out = out.model_copy(update={"audit_ref": str(meta.get("payload_id") or "")})
        record_system_event(
            ctx.db,
            level="WARNING",
            category="AI_LSG",
            message="LSG rejected tool args.",
            correlation_id=ctx.correlation_id,
            details={"request_id": req2.request_id, "tool": req2.tool_name, "error": err, "audit_ref": out.audit_ref},
        )
        return LsgExecution(policy=pol, duration_ms=duration_ms, raw_payload=None, result=out)

    # Rate limiting (remote only).
    if req2.source == "remote":
        per_min, per_sym = _rate_limits_for_tool(ctx.tm_cfg, req2.tool_name)
        if per_min is not None and not _RL.allow(key=f"tool:{req2.tool_name}", max_per_minute=per_min):
            duration_ms = int((time.perf_counter() - t0) * 1000)
            out = ToolResultEnvelope(
                request_id=req2.request_id,
                status="denied",
                denial_reason="rate_limit",
                data={"error": "rate_limited", "scope": "tool"},
                sanitization=ToolSanitizationMeta(),
            )
            meta = persist_operator_payload(
                ctx.db,
                decision_id=ctx.decision_id,
                tool_name=f"lsg.{req2.tool_name}",
                tool_call_id=req2.request_id,
                account_id=ctx.account_id,
                user_id=ctx.user_id,
                payload={"request": req2.model_dump(mode="json"), "error": "rate_limited:tool"},
            )
            out = out.model_copy(update={"audit_ref": str(meta.get("payload_id") or "")})
            return LsgExecution(policy=pol, duration_ms=duration_ms, raw_payload=None, result=out)
        if per_sym is not None:
            sym = _extract_symbol_key(args)
            if sym and not _RL.allow(key=f"tool:{req2.tool_name}:sym:{sym}", max_per_minute=per_sym):
                duration_ms = int((time.perf_counter() - t0) * 1000)
                out = ToolResultEnvelope(
                    request_id=req2.request_id,
                    status="denied",
                    denial_reason="rate_limit",
                    data={"error": "rate_limited", "scope": "symbol"},
                    sanitization=ToolSanitizationMeta(),
                )
                meta = persist_operator_payload(
                    ctx.db,
                    decision_id=ctx.decision_id,
                    tool_name=f"lsg.{req2.tool_name}",
                    tool_call_id=req2.request_id,
                    account_id=ctx.account_id,
                    user_id=ctx.user_id,
                    payload={"request": req2.model_dump(mode="json"), "error": "rate_limited:symbol", "symbol": sym},
                )
                out = out.model_copy(update={"audit_ref": str(meta.get("payload_id") or "")})
                return LsgExecution(policy=pol, duration_ms=duration_ms, raw_payload=None, result=out)

    # Execute.
    try:
        raw = await executor(args)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        out = ToolResultEnvelope(
            request_id=req2.request_id,
            status="error",
            denial_reason=None,
            data={"error": str(exc) or "tool_error"},
            sanitization=ToolSanitizationMeta(),
        )
        meta = persist_operator_payload(
            ctx.db,
            decision_id=ctx.decision_id,
            tool_name=f"lsg.{req2.tool_name}",
            tool_call_id=req2.request_id,
            account_id=ctx.account_id,
            user_id=ctx.user_id,
            payload={"request": req2.model_dump(mode="json"), "error": str(exc) or "tool_error"},
        )
        out = out.model_copy(update={"audit_ref": str(meta.get("payload_id") or "")})
        record_system_event(
            ctx.db,
            level="WARNING",
            category="AI_LSG",
            message="LSG tool execution error.",
            correlation_id=ctx.correlation_id,
            details={"request_id": req2.request_id, "tool": req2.tool_name, "error": out.data, "audit_ref": out.audit_ref},
        )
        return LsgExecution(policy=pol, duration_ms=duration_ms, raw_payload=None, result=out)

    duration_ms = int((time.perf_counter() - t0) * 1000)

    # Sanitize for remote. Local/legacy callers can ignore result.data and use raw_payload directly.
    sanit_meta = ToolSanitizationMeta()
    data = raw
    if req2.source == "remote":
        if computed_cap == ToolCapability.ACCOUNT_DIGEST or bucket_numbers:
            data, sanit_meta = sanitize_digest_payload(raw, settings=ctx.settings)
        else:
            data, sanit_meta = sanitize_kite_payload(req2.tool_name, raw, settings=ctx.settings, bucket_numbers=False)

    ok = ToolResultEnvelope(
        request_id=req2.request_id,
        status="ok",
        denial_reason=None,
        data=data,
        sanitization=sanit_meta,
        audit_ref=None,
    )
    meta = persist_operator_payload(
        ctx.db,
        decision_id=ctx.decision_id,
        tool_name=f"lsg.{req2.tool_name}",
        tool_call_id=req2.request_id,
        account_id=ctx.account_id,
        user_id=ctx.user_id,
        payload={
            "request": req2.model_dump(mode="json"),
            "result": {"status": "ok", "capability": computed_cap.value},
            # Keep raw stored locally for audit/debugging.
            "raw_payload": raw,
            # Keep a small view of remote-visible data too.
            "remote_data": data if req2.source == "remote" else None,
            "sanitization": sanit_meta.model_dump(mode="json"),
        },
    )
    ok = ok.model_copy(update={"audit_ref": str(meta.get("payload_id") or "")})
    record_system_event(
        ctx.db,
        level="INFO",
        category="AI_LSG",
        message="LSG executed tool request.",
        correlation_id=ctx.correlation_id,
        details={
            "request_id": req2.request_id,
            "tool": req2.tool_name,
            "source": req2.source,
            "capability": computed_cap.value,
            "duration_ms": duration_ms,
            "audit_ref": ok.audit_ref,
        },
    )

    return LsgExecution(policy=pol, duration_ms=duration_ms, raw_payload=raw, result=ok)


__all__ = [
    "LsgContext",
    "LsgExecution",
    "ToolRequestSource",
    "build_tool_request",
    "lsg_execute",
    "validate_args_against_schema",
]

