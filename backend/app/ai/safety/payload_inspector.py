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


def inspect_llm_payload(payload: Any, *, fail_closed: bool = True) -> list[PayloadFinding]:
    findings: list[PayloadFinding] = []
    _walk(payload, path="", findings=findings)
    if findings and fail_closed:
        raise PayloadInspectionError(
            message="Blocked outbound LLM request: payload contains forbidden keys/patterns.",
            findings=findings,
        )
    return findings


__all__ = ["PayloadFinding", "PayloadInspectionError", "inspect_llm_payload"]
