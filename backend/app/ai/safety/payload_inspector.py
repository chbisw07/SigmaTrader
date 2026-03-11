from __future__ import annotations

import re
from dataclasses import dataclass
import json
from typing import Any, Iterable


@dataclass(frozen=True)
class PayloadFinding:
    path: str
    kind: str  # key|pattern
    detail: str


class PayloadInspectionError(RuntimeError):
    def __init__(self, *, message: str, findings: list[PayloadFinding]) -> None:
        super().__init__(message)
        self.findings = findings


@dataclass
class PayloadSanitizationMeta:
    dropped_fields: list[str]
    redacted_fields: list[str]


_FORBIDDEN_KEYS_EXACT = {
    # OAuth / session / secrets.
    "request_token",
    "access_token",
    "refresh_token",
    "session_id",
    "auth_session_id",
    "api_key",
    "api_secret",
    "authorization",
    "cookie",
    "set-cookie",
    # Broker/account identifiers.
    "client_id",
    "user_id",
    "account_id",
    "broker_user_id",
    # Instrument identifiers.
    "instrument_token",
    "exchange_token",
    # Order identifiers (raw).
    "order_id",
    "exchange_order_id",
    "parent_order_id",
}

_FORBIDDEN_KEY_SUBSTR = (
    "token",
    "secret",
    "password",
    "passwd",
    "cookie",
    "bearer",
    "session",
)

_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
_PHONE_RE = re.compile(r"(?i)\b(?:\+?\d{1,3}[\s\-]?)?(?:\d[\s\-]?){9,12}\b")
_JWT_RE = re.compile(r"\beyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\b")
_API_KEY_LIKE_RE = re.compile(r"(?i)\b(sk-[a-z0-9]{10,}|ya29\.[a-z0-9\-_]+)\b")
# Heuristic for opaque secret-like strings. Exclude long pure-hex strings
# (hashes are common in our safe summaries) to reduce false positives.
_OPAQUE_SECRET_RE = re.compile(r"\b(?![0-9a-f]{32,}\b)[A-Za-z0-9_\-]{40,}\b")


def _is_forbidden_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return False
    if k in _FORBIDDEN_KEYS_EXACT:
        return True
    return any(sub in k for sub in _FORBIDDEN_KEY_SUBSTR)


def _iter_string_matches(s: str) -> Iterable[str]:
    for rx in (_EMAIL_RE, _JWT_RE, _API_KEY_LIKE_RE):
        if rx.search(s):
            yield rx.pattern
    # Phone + opaque secrets are noisy; only flag if they are long enough.
    if _PHONE_RE.search(s):
        yield "phone_like"
    if _OPAQUE_SECRET_RE.search(s):
        yield "opaque_secret_like"


def _walk(value: Any, *, path: str, findings: list[PayloadFinding]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            ks = str(k)
            p = f"{path}.{ks}" if path else ks
            if _is_forbidden_key(ks):
                findings.append(PayloadFinding(path=p, kind="key", detail=ks))
            _walk(v, path=p, findings=findings)
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            _walk(v, path=f"{path}[{i}]", findings=findings)
        return
    if isinstance(value, tuple):
        for i, v in enumerate(value):
            _walk(v, path=f"{path}[{i}]", findings=findings)
        return
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return
        # If this string looks like JSON, parse and inspect structurally. This avoids
        # false positives from regex scanning over serialized objects.
        if (s.startswith("{") or s.startswith("[")) and len(s) <= 200_000:
            try:
                obj = json.loads(s)
            except Exception:
                obj = None
            if obj is not None:
                _walk(obj, path=path, findings=findings)
                return
        for pat in _iter_string_matches(s):
            findings.append(PayloadFinding(path=path, kind="pattern", detail=pat))


def _sanitize_value(value: Any, *, path: str, meta: PayloadSanitizationMeta) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            ks = str(k)
            p = f"{path}.{ks}" if path else ks
            if _is_forbidden_key(ks):
                meta.dropped_fields.append(p)
                continue
            out[ks] = _sanitize_value(v, path=p, meta=meta)
        return out
    if isinstance(value, list):
        return [_sanitize_value(v, path=f"{path}[{i}]", meta=meta) for i, v in enumerate(value)]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(v, path=f"{path}[{i}]", meta=meta) for i, v in enumerate(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return value
        # If this string looks like JSON, sanitize structurally and re-serialize.
        if (s.startswith("{") or s.startswith("[")) and len(s) <= 200_000:
            try:
                obj = json.loads(s)
            except Exception:
                obj = None
            if obj is not None:
                clean = _sanitize_value(obj, path=path, meta=meta)
                try:
                    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
                except Exception:
                    return value
        # Redact secret/PII-like patterns in free text.
        redacted = value
        did = False
        for rx in (_EMAIL_RE, _PHONE_RE, _JWT_RE, _API_KEY_LIKE_RE, _OPAQUE_SECRET_RE):
            if rx.search(redacted):
                did = True
                redacted = rx.sub("[REDACTED]", redacted)
        if did:
            meta.redacted_fields.append(path or "$")
        return redacted
    return value


def sanitize_llm_payload(payload: Any) -> tuple[Any, PayloadSanitizationMeta]:
    """Best-effort sanitize an outbound payload so it can be sent to remote LLMs safely.

    - Drops forbidden keys (tokens/session/account identifiers/etc.)
    - Redacts email/phone/API-key/JWT/opaque-secret-like strings in free text.
    - If a string looks like JSON, sanitizes it structurally to avoid leaking forbidden keys.
    """
    meta = PayloadSanitizationMeta(dropped_fields=[], redacted_fields=[])
    return _sanitize_value(payload, path="", meta=meta), meta


def inspect_llm_payload(payload: Any, *, fail_closed: bool = True) -> list[PayloadFinding]:
    findings: list[PayloadFinding] = []
    _walk(payload, path="", findings=findings)
    if findings and fail_closed:
        raise PayloadInspectionError(
            message="Blocked outbound LLM request: payload contains forbidden keys/patterns.",
            findings=findings,
        )
    return findings


__all__ = [
    "PayloadFinding",
    "PayloadInspectionError",
    "PayloadSanitizationMeta",
    "inspect_llm_payload",
    "sanitize_llm_payload",
]
