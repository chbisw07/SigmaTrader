from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Final, Optional, Tuple

from app.core.config import Settings

PASSWORD_ALGORITHM: Final = "pbkdf2_sha256"
PASSWORD_ITERATIONS: Final = 260_000
PASSWORD_SALT_BYTES: Final = 16

SESSION_ALGORITHM: Final = "hs256"
SESSION_COOKIE_NAME: Final = "st_session"
SESSION_DEFAULT_TTL_SECONDS: Final = 60 * 60 * 24 * 7  # 7 days


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt.

    Format: ``algorithm$iterations$salt_b64$hash_b64``.
    """

    if not isinstance(password, str) or password == "":
        raise ValueError("Password must be a non-empty string.")

    salt = os.urandom(PASSWORD_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}"
        f"${_b64encode(salt)}${_b64encode(dk)}"
    )


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored hash."""

    try:
        algorithm, iter_str, salt_b64, hash_b64 = hashed.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iter_str)
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
    except Exception:
        return False

    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(dk, expected)


def _get_session_secret(settings: Settings) -> bytes:
    key = settings.crypto_key
    if not key:
        raise RuntimeError(
            "Crypto key not configured. Set ST_CRYPTO_KEY for session signing.",
        )
    return key.encode("utf-8")


def create_session_token(
    settings: Settings,
    user_id: int,
    ttl_seconds: Optional[int] = None,
) -> str:
    """Create an HMAC-signed session token carrying user id and expiry.

    Format: ``base64url(payload).base64url(signature)`` where payload is a JSON
    object with ``sub`` (user id), ``exp`` (Unix timestamp), and ``alg``.
    """

    if ttl_seconds is None:
        ttl_seconds = SESSION_DEFAULT_TTL_SECONDS

    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": int(time.time()) + int(ttl_seconds),
        "alg": SESSION_ALGORITHM,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8",
    )

    secret = _get_session_secret(settings)
    signature = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    return f"{_b64encode(payload_bytes)}.{_b64encode(signature)}"


def decode_session_token(
    settings: Settings,
    token: str,
) -> Tuple[int, dict[str, Any]]:
    """Decode and validate a session token.

    Returns ``(user_id, payload)`` if valid, otherwise raises ``ValueError``.
    """

    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid session token format.") from exc

    payload_bytes = _b64decode(payload_b64)
    signature = _b64decode(sig_b64)

    secret = _get_session_secret(settings)
    expected_sig = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("Invalid session token signature.")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid session token payload.") from exc

    if payload.get("alg") != SESSION_ALGORITHM:
        raise ValueError("Invalid session token algorithm.")

    exp = int(payload.get("exp", 0))
    if exp < int(time.time()):
        raise ValueError("Session token has expired.")

    user_id = int(payload.get("sub"))
    return user_id, payload


__all__ = [
    "hash_password",
    "verify_password",
    "create_session_token",
    "decode_session_token",
    "SESSION_COOKIE_NAME",
]
