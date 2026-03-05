from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Tuple

from app.core.config import Settings

from .lsg_types import ToolSanitizationMeta


_DROP_KEYS_EXACT = {
    # Secrets / tokens / auth.
    "access_token",
    "refresh_token",
    "request_token",
    "api_key",
    "api_secret",
    "password",
    "pin",
    "totp",
    "otp",
    "session_id",
    "auth_session_id",
    "authorization",
    "cookie",
    "set-cookie",
    # Identity / PII.
    "email",
    "phone",
    "mobile",
    "pan",
    "aadhar",
    "dob",
    "date_of_birth",
    "address",
    "name",
    # Broker identity ids (Tier-3): do not send to remote, even hashed.
    "client_id",
    "user_id",
    "broker_user_id",
    # Hidden identifiers (linkable).
    "instrument_token",
    "exchange_token",
}

_DROP_KEYS_SUBSTR = (
    "token",
    "secret",
    "password",
    "passwd",
    "cookie",
    "bearer",
    "session",
)

_HASH_KEYS_EXACT = {
    "order_id",
    "exchange_order_id",
    "parent_order_id",
    "trade_id",
    "transaction_id",
}

_HASH_KEYS_SUBSTR = (
    "order_id",
    "trade_id",
    "transaction_id",
)

_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
_JWT_RE = re.compile(r"\beyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\b")
_API_KEY_LIKE_RE = re.compile(r"(?i)\b(sk-[a-z0-9]{10,}|ya29\.[a-z0-9\-_]+)\b")
# Heuristic for opaque secret-like strings. Exclude long pure-hex strings
# (hashes are common in safe summaries) to reduce false positives.
_OPAQUE_SECRET_RE = re.compile(r"\b(?![0-9a-f]{32,}\b)[A-Za-z0-9_\-]{40,}\b")


def _key_norm(key: Any) -> str:
    return str(key or "").strip()


def _should_drop_key(k: str) -> bool:
    kn = (k or "").strip().lower()
    if not kn:
        return False
    if kn in _DROP_KEYS_EXACT:
        return True
    return any(sub in kn for sub in _DROP_KEYS_SUBSTR)


def _should_hash_key(k: str) -> bool:
    kn = (k or "").strip().lower()
    if not kn:
        return False
    if kn in _HASH_KEYS_EXACT:
        return True
    return any(sub == kn or sub in kn for sub in _HASH_KEYS_SUBSTR)


def _hash_id(settings: Settings, value: Any) -> str:
    # Salt with configured crypto key if present; stable across runs.
    salt = str(getattr(settings, "crypto_key", "") or getattr(settings, "ST_CRYPTO_KEY", "") or "")
    raw = f"{salt}:{str(value)}".encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()
    return f"h_{h[:16]}"


def _bucket_number(v: float) -> str:
    # Coarse buckets for digest-like outputs.
    av = abs(float(v))
    if av < 1:
        return "0-1"
    if av < 10:
        return "1-10"
    if av < 100:
        return "10-100"
    if av < 1_000:
        return "100-1k"
    if av < 10_000:
        return "1k-10k"
    if av < 100_000:
        return "10k-100k"
    if av < 1_000_000:
        return "100k-1m"
    return ">=1m"


_SENSITIVE_NUMERIC_KEY_SUBSTR = (
    "qty",
    "quantity",
    "price",
    "avg",
    "ltp",
    "margin",
    "util",
    "available",
    "cash",
    "equity",
    "pnl",
    "value",
    "notional",
    "amount",
    "exposure",
    "loss",
)


def _should_bucket_numeric(key_path: str) -> bool:
    # Bucket only numeric values that are plausibly sensitive. Avoid bucketing
    # obvious counters like "count", "n", etc.
    p = (key_path or "").strip().lower()
    if not p:
        return False
    last = p.split(".")[-1]
    if last in {"count", "counts", "n", "num", "total"}:
        return False
    return any(sub in last for sub in _SENSITIVE_NUMERIC_KEY_SUBSTR)


def _paths_append(meta_list: list[str], path: str, *, limit: int = 200) -> None:
    if len(meta_list) >= limit:
        return
    meta_list.append(path)


def _sanitize(
    settings: Settings,
    value: Any,
    *,
    path: str,
    meta: ToolSanitizationMeta,
    bucket_numbers: bool,
) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            ks = _key_norm(k)
            p = f"{path}.{ks}" if path else ks
            if _should_drop_key(ks):
                _paths_append(meta.redacted_fields, p)
                continue
            if _should_hash_key(ks) and v is not None:
                out[ks] = _hash_id(settings, v)
                _paths_append(meta.hashed_fields, p)
                continue
            out[ks] = _sanitize(settings, v, path=p, meta=meta, bucket_numbers=bucket_numbers)
        return out
    if isinstance(value, list):
        return [_sanitize(settings, v, path=f"{path}[{i}]", meta=meta, bucket_numbers=bucket_numbers) for i, v in enumerate(value)]
    if isinstance(value, tuple):
        return tuple(
            _sanitize(settings, v, path=f"{path}[{i}]", meta=meta, bucket_numbers=bucket_numbers) for i, v in enumerate(value)
        )
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return value
        # Drop obvious PII/secret patterns even if the key name isn't flagged.
        if _EMAIL_RE.search(s) or _JWT_RE.search(s) or _API_KEY_LIKE_RE.search(s) or _OPAQUE_SECRET_RE.search(s):
            _paths_append(meta.redacted_fields, path or "$")
            return "[REDACTED]"
        return value
    if bucket_numbers and isinstance(value, (int, float)) and _should_bucket_numeric(path):
        _paths_append(meta.bucketed_fields, path or "$")
        return _bucket_number(float(value))
    return value


def sanitize_kite_payload(
    tool_name: str,
    payload: Any,
    *,
    settings: Settings,
    bucket_numbers: bool = False,
) -> Tuple[Any, ToolSanitizationMeta]:
    """Sanitize any payload before returning it to a remote reasoner.

    This is a defense-in-depth layer. Policy should still prevent returning raw
    holdings/orders/margins/trades payloads to remote models.
    """
    _ = tool_name  # reserved for future tool-specific shaping
    meta = ToolSanitizationMeta()
    data = _sanitize(settings, payload, path="", meta=meta, bucket_numbers=bucket_numbers)
    return data, meta


def sanitize_digest_payload(payload: Any, *, settings: Settings) -> Tuple[Any, ToolSanitizationMeta]:
    # Digests are always bucketed.
    return sanitize_kite_payload("digest", payload, settings=settings, bucket_numbers=True)


def redact_keys_for_remote(keys: Iterable[str]) -> list[str]:
    """Helper for callers to prefilter known-bad keys."""
    out: list[str] = []
    for k in keys:
        ks = _key_norm(k)
        if not ks:
            continue
        if _should_drop_key(ks):
            continue
        out.append(ks)
    return out


__all__ = ["sanitize_digest_payload", "sanitize_kite_payload", "redact_keys_for_remote"]
