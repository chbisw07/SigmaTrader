from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import SystemEvent
from app.schemas.ai_settings import (
    AiAuditResponse,
    AiSettings,
    AiSettingsUpdate,
    KiteMcpStatus,
    KiteMcpTestRequest,
    KiteMcpTestResponse,
)
from app.clients.kite_mcp import HttpKiteMCPClient
from app.services.ai_trading_manager.ai_settings_config import (
    apply_ai_settings_update,
    get_ai_settings_with_source,
    is_execution_hard_disabled,
    set_ai_settings,
    should_allow_execution_enable,
)
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _corr() -> str:
    return uuid4().hex


@router.get("", response_model=AiSettings)
def read_ai_settings(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiSettings:
    cfg, _src = get_ai_settings_with_source(db, settings)
    return cfg


@router.put("", response_model=AiSettings)
def update_ai_settings(
    payload: AiSettingsUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiSettings:
    existing, _src = get_ai_settings_with_source(db, settings)
    try:
        merged = apply_ai_settings_update(existing=existing, update=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Hard safety: if execution is being enabled, require connected MCP.
    if payload.feature_flags and payload.feature_flags.ai_execution_enabled is True:
        ok, reason = should_allow_execution_enable(merged)
        if not ok:
            raise HTTPException(status_code=400, detail=reason or "Cannot enable execution.")

    # If kill switch is active, execution is effectively disabled; keep it auditable.
    if merged.feature_flags.ai_execution_enabled and is_execution_hard_disabled(merged):
        # Keep ai_execution_enabled as requested, but record warning in audit.
        record_system_event(
            db,
            level="WARNING",
            category="AI_SETTINGS",
            message="AI execution enabled while kill switch is active.",
            correlation_id=_corr(),
            details={"kill_switch": merged.kill_switch.model_dump(mode="json")},
        )

    set_ai_settings(db, settings, merged)
    record_system_event(
        db,
        level="INFO",
        category="AI_SETTINGS",
        message="AI settings updated.",
        correlation_id=_corr(),
        details={
            "feature_flags": merged.feature_flags.model_dump(mode="json"),
            "kite_mcp": {
                "server_url": merged.kite_mcp.server_url,
                "transport_mode": merged.kite_mcp.transport_mode,
                "auth_method": merged.kite_mcp.auth_method,
                "auth_profile_ref": merged.kite_mcp.auth_profile_ref,
                "scopes": merged.kite_mcp.scopes.model_dump(mode="json"),
                "last_status": merged.kite_mcp.last_status.value,
            },
            "llm_provider": {
                "enabled": merged.llm_provider.enabled,
                "provider": merged.llm_provider.provider.value,
                "model": merged.llm_provider.model,
                "do_not_send_pii": merged.llm_provider.do_not_send_pii,
                "limits": merged.llm_provider.limits.model_dump(mode="json"),
            },
        },
    )
    return merged


@router.post("/kite/test", response_model=KiteMcpTestResponse)
def test_kite_mcp_connection(
    payload: KiteMcpTestRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpTestResponse:
    cfg, _src = get_ai_settings_with_source(db, settings)

    # Allow overriding the URL (e.g. user typed and hit Test before saving).
    if payload.server_url is not None:
        try:
            cfg = apply_ai_settings_update(
                existing=cfg,
                update=AiSettingsUpdate(kite_mcp={"server_url": payload.server_url}),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    server_url = (cfg.kite_mcp.server_url or "").strip()
    if not server_url:
        raise HTTPException(status_code=400, detail="Kite MCP server URL is not configured.")

    client = HttpKiteMCPClient(timeout_seconds=5)
    checked = datetime.now(UTC)
    result = client.test_connection(server_url=server_url, fetch_capabilities=bool(payload.fetch_capabilities))

    cfg.kite_mcp.last_checked_ts = checked
    cfg.kite_mcp.last_status = KiteMcpStatus.connected if result.ok else KiteMcpStatus.error
    cfg.kite_mcp.last_error = None if result.ok else (result.error or "Kite MCP connection test failed.")

    cache: Dict[str, Any] = {}
    if result.used_endpoint:
        cache["used_endpoint"] = result.used_endpoint
    if result.status_code is not None:
        cache["status_code"] = int(result.status_code)
    if result.health is not None:
        cache["health"] = result.health
    if result.capabilities is not None:
        cache["capabilities"] = result.capabilities
    if cache:
        cfg.kite_mcp.capabilities_cache = cache

    set_ai_settings(db, settings, cfg)
    record_system_event(
        db,
        level="INFO" if result.ok else "WARNING",
        category="KITE_MCP",
        message="Kite MCP connection test completed." if result.ok else "Kite MCP connection test failed.",
        correlation_id=_corr(),
        details={
            "server_url": server_url,
            "status": cfg.kite_mcp.last_status.value,
            "checked_ts": checked.isoformat(),
            "error": cfg.kite_mcp.last_error,
            "capabilities_cache": cfg.kite_mcp.capabilities_cache,
        },
    )

    return KiteMcpTestResponse(
        status=cfg.kite_mcp.last_status,
        checked_ts=checked,
        error=cfg.kite_mcp.last_error,
        capabilities=cfg.kite_mcp.capabilities_cache or {},
    )


@router.get("/audit", response_model=AiAuditResponse)
def list_ai_audit_events(
    level: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> AiAuditResponse:
    cats = {"AI_SETTINGS", "KITE_MCP"}
    if category is not None:
        # Allow filtering to one of the AI categories.
        c = category.strip().upper()
        if c in cats:
            cats = {c}
    q = db.query(SystemEvent).filter(SystemEvent.category.in_(sorted(cats)))
    if level is not None:
        q = q.filter(SystemEvent.level == level.strip().upper())
    rows: List[SystemEvent] = (
        q.order_by(SystemEvent.created_at.desc())  # type: ignore[arg-type]
        .offset(int(offset))
        .limit(int(limit))
        .all()
    )
    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "level": r.level,
                "category": r.category,
                "message": r.message,
                "details": r.details,
                "correlation_id": r.correlation_id,
                "created_at": r.created_at,
            }
        )
    next_offset = int(offset) + len(items)
    return AiAuditResponse(items=items, next_offset=next_offset)
