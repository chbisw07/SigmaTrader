from __future__ import annotations

import hashlib
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
    AiTestRequest,
    AiTestResponse,
    DiscoverModelsRequest,
    DiscoverModelsResponse,
    ModelEntry,
    ProviderDescriptor,
)
from app.services.ai.active_config import (
    apply_config_update,
    get_active_config,
    set_active_config,
)
from app.services.ai.provider_keys import (
    create_key,
    decrypt_key_value,
    delete_key,
    get_key,
    list_keys,
    update_key,
)
from app.services.ai.provider_registry import get_provider, list_providers
from app.services.ai.providers.base import ProviderAuthError, ProviderConfigError, ProviderError
from app.services.ai.providers.factory import build_provider_client
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


def _require_llm_enabled(db: Session, settings: Settings) -> AiActiveConfig:
    cfg, _src = get_active_config(db, settings)
    if not cfg.enabled:
        raise HTTPException(
            status_code=403,
            detail="AI provider is disabled. Enable it in Settings → AI.",
        )
    return cfg


def _safe_prompt_audit(prompt: str, *, do_not_send_pii: bool) -> dict:
    p = prompt or ""
    h = hashlib.sha256(p.encode("utf-8")).hexdigest()
    if do_not_send_pii:
        return {"prompt_hash": h, "prompt_len": len(p)}
    preview = p.strip().replace("\n", " ")
    if len(preview) > 120:
        preview = preview[:120] + "…"
    return {"prompt_hash": h, "prompt_len": len(p), "prompt_preview": preview}


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


@router.post("/models/discover", response_model=DiscoverModelsResponse)
def discover_models(
    payload: DiscoverModelsRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DiscoverModelsResponse:
    _require_llm_enabled(db, settings)
    info = get_provider(payload.provider)
    if info is None or not info.supports_model_discovery:
        raise HTTPException(status_code=400, detail="Unsupported provider.")

    base_url = payload.base_url or info.default_base_url
    api_key: str | None = None
    if info.requires_api_key:
        if payload.key_id is None:
            raise HTTPException(status_code=400, detail="key_id is required for this provider.")
        row = get_key(db, key_id=int(payload.key_id), user_id=None)
        if row is None:
            raise HTTPException(status_code=404, detail="Key not found.")
        if row.provider != info.id:
            raise HTTPException(status_code=400, detail="Key provider mismatch.")
        api_key = decrypt_key_value(settings, row)

    try:
        client = build_provider_client(provider_id=info.id, api_key=api_key, base_url=base_url)
        try:
            models = client.discover_models()
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
    except ProviderAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Unauthorized.") from exc
    except ProviderConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DiscoverModelsResponse(
        models=[
            ModelEntry(
                id=m.id,
                label=m.label,
                source=m.source,
                raw=m.raw or {},
            )
            for m in models
        ]
    )


@router.post("/test", response_model=AiTestResponse)
def run_ai_test(
    payload: AiTestRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiTestResponse:
    cfg = _require_llm_enabled(db, settings)

    provider_id = (payload.provider or cfg.provider or "").strip().lower()
    info = get_provider(provider_id)
    if info is None or not info.supports_test:
        raise HTTPException(status_code=400, detail="Unsupported provider.")

    model = (payload.model or cfg.model or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model is required.")

    base_url = payload.base_url or cfg.base_url or info.default_base_url
    api_key: str | None = None
    key_id = payload.key_id if payload.key_id is not None else cfg.active_key_id
    if info.requires_api_key:
        if key_id is None:
            raise HTTPException(status_code=400, detail="API key is required for this provider.")
        row = get_key(db, key_id=int(key_id), user_id=None)
        if row is None:
            raise HTTPException(status_code=404, detail="Key not found.")
        if row.provider != info.id:
            raise HTTPException(status_code=400, detail="Key provider mismatch.")
        api_key = decrypt_key_value(settings, row)

    status = "ok"
    latency_ms_for_audit: int | None = None
    try:
        client = build_provider_client(provider_id=info.id, api_key=api_key, base_url=base_url)
        try:
            res = client.run_test(model=model, prompt=payload.prompt)
            latency_ms_for_audit = int(res.latency_ms)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
    except ProviderAuthError as exc:
        status = "auth_error"
        raise HTTPException(status_code=400, detail=str(exc) or "Unauthorized.") from exc
    except ProviderConfigError as exc:
        status = "config_error"
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        status = "error"
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        record_system_event(
            db,
            level="INFO" if status == "ok" else "WARNING",
            category="AI_PROVIDER",
            message="AI test prompt executed." if status == "ok" else "AI test prompt failed.",
            correlation_id=_corr(),
            details={
                "event_type": "AI_TEST_RUN",
                "provider": info.id,
                "model": model,
                "base_url": base_url,
                "status": status,
                "latency_ms": latency_ms_for_audit,
                **_safe_prompt_audit(payload.prompt, do_not_send_pii=bool(cfg.do_not_send_pii)),
            },
        )

    usage = res.usage or {}
    return AiTestResponse(
        text=res.text,
        latency_ms=int(res.latency_ms),
        usage={
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        raw_metadata=res.raw_metadata or {},
    )


__all__ = ["router"]
