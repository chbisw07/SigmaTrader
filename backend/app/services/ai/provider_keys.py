from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import AiProviderKey


def mask_api_key(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return "****"
    if len(v) <= 8:
        return "****"
    prefix = v[:3]
    suffix = v[-4:]
    return f"{prefix}…{suffix}"


def _meta_to_json(meta: Dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    try:
        return json.dumps(meta, ensure_ascii=False, sort_keys=True)
    except Exception:
        return None


def _meta_from_json(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def list_keys(
    db: Session,
    *,
    provider: str,
    user_id: int | None = None,
) -> List[AiProviderKey]:
    p = (provider or "").strip().lower()
    return (
        db.query(AiProviderKey)
        .filter(AiProviderKey.provider == p, AiProviderKey.user_id.is_(user_id))
        .order_by(AiProviderKey.created_at.desc())
        .all()
    )


def get_key(
    db: Session,
    *,
    key_id: int,
    user_id: int | None = None,
) -> AiProviderKey | None:
    return (
        db.query(AiProviderKey)
        .filter(AiProviderKey.id == int(key_id), AiProviderKey.user_id.is_(user_id))
        .one_or_none()
    )


def decrypt_key_value(settings: Settings, row: AiProviderKey) -> str:
    return decrypt_token(settings, row.key_ciphertext)


def create_key(
    db: Session,
    settings: Settings,
    *,
    provider: str,
    key_name: str,
    api_key_value: str,
    meta: Dict[str, Any] | None = None,
    user_id: int | None = None,
) -> AiProviderKey:
    p = (provider or "").strip().lower()
    name = (key_name or "").strip()
    if not p:
        raise ValueError("provider is required.")
    if not name:
        raise ValueError("key_name is required.")
    value = (api_key_value or "").strip()
    if not value:
        raise ValueError("api_key_value is required.")

    masked = mask_api_key(value)
    ciphertext = encrypt_token(settings, value)
    now = datetime.now(UTC)
    row = AiProviderKey(
        user_id=user_id,
        provider=p,
        key_name=name,
        key_ciphertext=ciphertext,
        key_masked=masked,
        meta_json=_meta_to_json(meta),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_key(
    db: Session,
    settings: Settings,
    *,
    key_id: int,
    user_id: int | None = None,
    key_name: str | None = None,
    api_key_value: str | None = None,
    meta: Dict[str, Any] | None = None,
) -> AiProviderKey:
    row = get_key(db, key_id=key_id, user_id=user_id)
    if row is None:
        raise ValueError("Key not found.")

    changed = False
    if key_name is not None:
        name = (key_name or "").strip()
        if not name:
            raise ValueError("key_name cannot be empty.")
        row.key_name = name
        changed = True

    if api_key_value is not None:
        value = (api_key_value or "").strip()
        if not value:
            raise ValueError("api_key_value cannot be empty.")
        row.key_ciphertext = encrypt_token(settings, value)
        row.key_masked = mask_api_key(value)
        changed = True

    if meta is not None:
        row.meta_json = _meta_to_json(meta)
        changed = True

    if changed:
        row.updated_at = datetime.now(UTC)
        db.add(row)
        db.commit()
        db.refresh(row)

    return row


def delete_key(
    db: Session,
    *,
    key_id: int,
    user_id: int | None = None,
) -> bool:
    row = get_key(db, key_id=key_id, user_id=user_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


__all__ = [
    "create_key",
    "decrypt_key_value",
    "delete_key",
    "get_key",
    "list_keys",
    "mask_api_key",
    "update_key",
    "_meta_from_json",
]
