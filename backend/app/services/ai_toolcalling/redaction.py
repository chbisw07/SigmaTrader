from __future__ import annotations

import re
from typing import Any


_SENSITIVE_KEY_EXACT = {
    # Secrets/tokens.
    "api_key",
    "api_secret",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "totp",
    "otp",
    "pin",
    "request_token",
    "checksum",
    "signature",
    # Session identifiers.
    "session_id",
    "auth_session_id",
    # Broker/account identifiers.
    "user_id",
    "client_id",
    "account_id",
    "broker_user_id",
    # Order identifiers.
    "order_id",
    "exchange_order_id",
    "parent_order_id",
}

_SENSITIVE_KEY_SUBSTR = (
    "secret",
    "password",
    "passwd",
    "token",
    "bearer",
    "session",
    "cookie",
)

_PII_KEY_SUBSTR = (
    "email",
    "phone",
    "mobile",
    "pan",
    "aadhar",
    "address",
)

_LIKELY_TOKEN_RE = re.compile(r"(?i)\b(sk-[A-Za-z0-9]{10,}|ya29\.[A-Za-z0-9\-_]+)\b")


def _mask_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        s = str(value)
        # Keep last 2 digits only.
        if len(s) <= 2:
            return "***"
        return f"***{s[-2:]}"
    if isinstance(value, (bytes, bytearray)):
        return "***"
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return s
        # Mask known token shapes even if the key name wasn't flagged.
        if _LIKELY_TOKEN_RE.search(s):
            return _LIKELY_TOKEN_RE.sub(lambda m: _mask_string(m.group(0)), s)
        return _mask_string(s)
    return "***"


def _mask_string(s: str) -> str:
    if len(s) <= 8:
        return "***"
    return f"{s[:2]}…{s[-4:]}"


def _is_sensitive_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return False
    if k in _SENSITIVE_KEY_EXACT:
        return True
    if any(sub in k for sub in _SENSITIVE_KEY_SUBSTR):
        return True
    if any(sub in k for sub in _PII_KEY_SUBSTR):
        return True
    return False


def redact_for_llm(value: Any) -> Any:
    """
    Best-effort deterministic redaction for content that may be forwarded to an LLM.

    This is intentionally conservative: it masks secrets/tokens, session identifiers,
    broker/account identifiers, and common PII-like fields.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            ks = str(k)
            if _is_sensitive_key(ks):
                out[ks] = _mask_scalar(v)
            else:
                out[ks] = redact_for_llm(v)
        return out
    if isinstance(value, list):
        return [redact_for_llm(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_for_llm(v) for v in value)
    return value


__all__ = ["redact_for_llm"]
