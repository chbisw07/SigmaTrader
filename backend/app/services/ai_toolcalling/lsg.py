from __future__ import annotations

import hashlib
import json
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


def _as_str_list(v: Any) -> list[str] | None:
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    if isinstance(v, list):
        out: list[str] = []
        for row in v:
            if isinstance(row, str) and row.strip():
                out.append(row.strip())
        return out
    return None


def _normalize_args_for_tool(
    *,
    tool_name: str,
    args: dict[str, Any],
    schema: dict[str, Any] | None,
    strict: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize common remote arg shapes to match MCP tool schemas.

    Remote requests are validated strictly (unknown keys are rejected). In practice,
    remote LLMs often emit close-but-not-exact arg keys. Normalization improves
    convergence of the remote tool loop without weakening policy-gating.
    """
    if not strict or not schema or not isinstance(schema, dict):
        return args, {}

    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    required = schema.get("required")
    req = required if isinstance(required, list) else []
    wanted = set(str(k) for k in props.keys() if str(k))
    wanted |= set(str(k) for k in req if str(k))

    out = dict(args or {})
    changed: dict[str, Any] = {}

    # Market-data tools: accept symbols/tradingsymbols and map them to instruments.
    if "instruments" in wanted and "instruments" not in out:
        used_key = ""
        cand: Any = None
        for k in ("symbols", "symbol", "tradingsymbols", "tradingsymbol", "instrument"):
            if k in out:
                used_key = k
                cand = out.get(k)
                break
        items = _as_str_list(cand)
        if items:
            exch = str(out.get("exchange") or "NSE").strip().upper() or "NSE"
            norm: list[str] = []
            for s in items:
                ss = str(s).strip()
                if not ss:
                    continue
                if ":" in ss:
                    norm.append(ss.upper())
                else:
                    norm.append(f"{exch}:{ss.upper()}")
            if norm:
                out["instruments"] = norm
                changed["instruments"] = {"from": used_key or "unknown", "count": len(norm)}

    # search_instruments expects "query".
    if tool_name == "search_instruments" and "query" in wanted and "query" not in out:
        q = out.get("symbol") or out.get("tradingsymbol")
        if isinstance(q, str) and q.strip():
            out["query"] = q.strip()
            changed["query"] = {"from": "symbol/tradingsymbol"}

    # get_historical_data expects instrument_token (int). Remote models commonly emit alternate key shapes.
    if "instrument_token" in wanted:
        if "instrument_token" not in out:
            used_key = ""
            cand: Any = None
            for k in ("instrumentToken", "instrument_id", "instrumentId", "token", "instrument"):
                if k in out:
                    used_key = k
                    cand = out.get(k)
                    break
            tok: int | None = None
            if isinstance(cand, int) and not isinstance(cand, bool):
                tok = cand
            elif isinstance(cand, float) and cand.is_integer():
                tok = int(cand)
            elif isinstance(cand, str) and cand.strip().isdigit():
                tok = int(cand.strip())
            if tok is not None:
                out["instrument_token"] = tok
                changed["instrument_token"] = {"from": used_key or "unknown"}
        else:
            cand = out.get("instrument_token")
            if isinstance(cand, float) and cand.is_integer():
                out["instrument_token"] = int(cand)
                changed["instrument_token"] = {"from": "float->int"}
            elif isinstance(cand, str) and cand.strip().isdigit():
                out["instrument_token"] = int(cand.strip())
                changed["instrument_token"] = {"from": "str->int"}

    # Drop unknown keys (post-normalization) so strict schema validation can pass.
    if wanted:
        dropped = [k for k in list(out.keys()) if k not in wanted]
        if dropped:
            for k in dropped:
                out.pop(k, None)
            changed["dropped_keys"] = dropped

    return out, changed


def _invalid_args_hint(*, tool_name: str, err: str | None) -> str:
    n = (tool_name or "").strip()
    e = (err or "").strip()
    if n == "get_historical_data" and "instrument_token" in e:
        return (
            "get_historical_data requires `instrument_token` (int). "
            "If you only have a symbol, first call `search_instruments` with `query` (e.g. 'SBIN' or 'NSE:SBIN'), "
            "then retry get_historical_data using the returned instrument_token."
        )
    if n in ("search_instruments", "get_ltp", "get_quotes", "get_ohlc", "get_historical_data"):
        return "Fix args to match the MCP schema (required keys + correct types). For symbol lists, provide instruments like ['NSE:INFY']."
    return "Fix args to match the MCP schema (required keys + correct types)."


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
                "telemetry_tier": getattr(pol, "telemetry_tier", None).value if getattr(pol, "telemetry_tier", None) else None,
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
                "telemetry_tier": getattr(pol, "telemetry_tier", None).value if getattr(pol, "telemetry_tier", None) else None,
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

    args, norm_meta = _normalize_args_for_tool(
        tool_name=str(req2.tool_name or ""),
        args=args,
        schema=tool_input_schema,
        strict=strict,
    )

    err = validate_args_against_schema(schema=tool_input_schema, args=args, strict=strict)
    if err:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        out = ToolResultEnvelope(
            request_id=req2.request_id,
            status="denied",
            denial_reason="invalid_args",
            data={
                "error": err,
                "hint": _invalid_args_hint(tool_name=str(req2.tool_name or ""), err=err),
                "normalized_args": norm_meta or None,
            },
            sanitization=ToolSanitizationMeta(),
        )
        meta = persist_operator_payload(
            ctx.db,
            decision_id=ctx.decision_id,
            tool_name=f"lsg.{req2.tool_name}",
            tool_call_id=req2.request_id,
            account_id=ctx.account_id,
            user_id=ctx.user_id,
            payload={"request": req2.model_dump(mode="json"), "normalized_args": norm_meta or None, "error": err},
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
            payload={
                "request": req2.model_dump(mode="json"),
                "error": str(exc) or "tool_error",
                "telemetry_tier": getattr(pol, "telemetry_tier", None).value if getattr(pol, "telemetry_tier", None) else None,
            },
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
    payload_obj: dict[str, Any] = {
        "request": req2.model_dump(mode="json"),
        "result": {"status": "ok", "capability": computed_cap.value},
        "sanitization": sanit_meta.model_dump(mode="json"),
        "telemetry_tier": getattr(pol, "telemetry_tier", None).value if getattr(pol, "telemetry_tier", None) else None,
    }
    if req2.source == "remote":
        # Do not store raw payload for remote requests (may contain Tier-3 values).
        try:
            raw_json = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
            payload_obj["raw_payload_sha256"] = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            payload_obj["raw_payload_type"] = type(raw).__name__
            payload_obj["raw_payload_items_hint"] = 0 if raw is None else (len(raw) if isinstance(raw, (list, dict)) else 1)
        except Exception:
            payload_obj["raw_payload_sha256"] = None
        payload_obj["remote_data"] = data
    else:
        # Keep raw stored locally for non-remote sources (local/system/legacy).
        payload_obj["raw_payload"] = raw
        payload_obj["remote_data"] = None

    meta = persist_operator_payload(
        ctx.db,
        decision_id=ctx.decision_id,
        tool_name=f"lsg.{req2.tool_name}",
        tool_call_id=req2.request_id,
        account_id=ctx.account_id,
        user_id=ctx.user_id,
        payload=payload_obj,
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
            "telemetry_tier": getattr(pol, "telemetry_tier", None).value if getattr(pol, "telemetry_tier", None) else None,
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
