from __future__ import annotations

from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.ai_provider import (
    AiActiveConfig,
    AiActiveConfigUpdate,
    AiProviderKeyCreate,
    AiProviderKeyRead,
    AiProviderKeyUpdate,
    ProviderDescriptor,
)
from app.services.ai.active_config import (
    apply_config_update,
    get_active_config,
    set_active_config,
)
from app.services.ai.provider_keys import create_key, delete_key, get_key, list_keys, update_key
from app.services.ai.provider_registry import get_provider, list_providers
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _corr() -> str:
    return uuid4().hex


def _to_key_read(row) -> AiProviderKeyRead:
    return AiProviderKeyRead(
        id=row.id,
        provider=row.provider,
        key_name=row.key_name,
        key_masked=row.key_masked,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/providers", response_model=List[ProviderDescriptor])
def list_ai_providers() -> List[ProviderDescriptor]:
    items: List[ProviderDescriptor] = []
    for p in list_providers():
        # Hide deprecated/unhelpful providers from the UI contract for now.
        if p.id == "anthropic":
            continue
        items.append(
            ProviderDescriptor(
                id=p.id,
                label=p.label,
                kind=p.kind,
                requires_api_key=p.requires_api_key,
                supports_base_url=p.supports_base_url,
                default_base_url=p.default_base_url,
                supports_model_discovery=p.supports_model_discovery,
                supports_test=p.supports_test,
            )
        )
    return items


@router.get("/config", response_model=AiActiveConfig)
def read_ai_provider_config(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiActiveConfig:
    cfg, _src = get_active_config(db, settings)
    if cfg.active_key_id is not None:
        row = get_key(db, key_id=int(cfg.active_key_id), user_id=None)
        if row is not None:
            cfg.active_key = _to_key_read(row)
    return cfg


@router.put("/config", response_model=AiActiveConfig)
def update_ai_provider_config(
    payload: AiActiveConfigUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiActiveConfig:
    existing, _src = get_active_config(db, settings)
    try:
        merged = apply_config_update(db, settings, existing=existing, update=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    set_active_config(db, settings, merged)
    record_system_event(
        db,
        level="INFO",
        category="AI_PROVIDER",
        message="AI provider config updated.",
        correlation_id=_corr(),
        details={
            "event_type": "AI_CONFIG_UPDATED",
            "enabled": merged.enabled,
            "provider": merged.provider,
            "model": merged.model,
            "base_url": merged.base_url,
            "active_key_id": merged.active_key_id,
            "do_not_send_pii": merged.do_not_send_pii,
            "limits": merged.limits.model_dump(mode="json"),
        },
    )

    if merged.active_key_id is not None:
        row = get_key(db, key_id=int(merged.active_key_id), user_id=None)
        if row is not None:
            merged.active_key = _to_key_read(row)
    return merged


@router.get("/keys", response_model=List[AiProviderKeyRead])
def list_ai_provider_keys(
    provider: str = Query(...),
    db: Session = Depends(get_db),
) -> List[AiProviderKeyRead]:
    info = get_provider(provider)
    if info is None:
        raise HTTPException(status_code=400, detail="Unsupported provider.")
    rows = list_keys(db, provider=info.id, user_id=None)
    return [_to_key_read(r) for r in rows]


@router.post("/keys", response_model=AiProviderKeyRead, status_code=201)
def create_ai_provider_key(
    payload: AiProviderKeyCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiProviderKeyRead:
    info = get_provider(payload.provider)
    if info is None:
        raise HTTPException(status_code=400, detail="Unsupported provider.")
    try:
        row = create_key(
            db,
            settings,
            provider=info.id,
            key_name=payload.key_name,
            api_key_value=payload.api_key_value,
            meta=payload.meta,
            user_id=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_system_event(
        db,
        level="INFO",
        category="AI_PROVIDER",
        message="AI provider key created.",
        correlation_id=_corr(),
        details={
            "event_type": "AI_KEY_CREATED",
            "provider": info.id,
            "key_id": row.id,
            "key_name": row.key_name,
            "key_masked": row.key_masked,
        },
    )
    return _to_key_read(row)


@router.put("/keys/{key_id}", response_model=AiProviderKeyRead)
def update_ai_provider_key(
    key_id: int,
    payload: AiProviderKeyUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiProviderKeyRead:
    try:
        row = update_key(
            db,
            settings,
            key_id=int(key_id),
            user_id=None,
            key_name=payload.key_name,
            api_key_value=payload.api_key_value,
            meta=payload.meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_system_event(
        db,
        level="INFO",
        category="AI_PROVIDER",
        message="AI provider key updated.",
        correlation_id=_corr(),
        details={
            "event_type": "AI_KEY_UPDATED",
            "provider": row.provider,
            "key_id": row.id,
            "key_name": row.key_name,
            "key_masked": row.key_masked,
        },
    )
    return _to_key_read(row)


@router.delete("/keys/{key_id}", status_code=204)
def delete_ai_provider_key(
    key_id: int,
    db: Session = Depends(get_db),
) -> None:
    row = get_key(db, key_id=int(key_id), user_id=None)
    if row is None:
        raise HTTPException(status_code=404, detail="Key not found.")
    ok = delete_key(db, key_id=int(key_id), user_id=None)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found.")
    record_system_event(
        db,
        level="INFO",
        category="AI_PROVIDER",
        message="AI provider key deleted.",
        correlation_id=_corr(),
        details={
            "event_type": "AI_KEY_DELETED",
            "provider": row.provider,
            "key_id": row.id,
            "key_name": row.key_name,
            "key_masked": row.key_masked,
        },
    )
    return None


__all__ = ["router"]
