from __future__ import annotations

import base64
from typing import Final

from app.core.config import Settings


def _get_key_bytes(settings: Settings) -> bytes:
    key = settings.crypto_key
    if not key:
        raise RuntimeError(
            "Crypto key not configured. Set ST_CRYPTO_KEY in your environment/.env.",
        )
    return key.encode("utf-8")


def encrypt_token(settings: Settings, token: str) -> str:
    """Lightweight symmetric encryption for access tokens.

    This uses a simple XOR with an environment-provided key and Base64
    encoding. It is **not** a substitute for strong encryption but is
    sufficient to avoid storing tokens in plain text for a local,
    single-user tool. For stronger guarantees, swap this out for a
    library such as `cryptography.fernet`.
    """

    key_bytes = _get_key_bytes(settings)
    token_bytes = token.encode("utf-8")
    encrypted = bytes(
        b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(token_bytes)
    )
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_token(settings: Settings, encrypted: str) -> str:
    key_bytes = _get_key_bytes(settings)
    data = base64.urlsafe_b64decode(encrypted.encode("ascii"))
    decrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
    return decrypted.decode("utf-8")


__all__: Final = ["encrypt_token", "decrypt_token"]
