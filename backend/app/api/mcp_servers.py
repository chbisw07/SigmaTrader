from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api import ai_settings as ai_settings_api
from app.api import kite_mcp as kite_mcp_api
from app.clients.mcp_sse import McpError, McpSseClient
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.ai_settings import AiSettingsUpdate, KiteMcpStatus, KiteMcpTestRequest
from app.schemas.kite_mcp import KiteMcpAuthStartResponse, KiteMcpStatusResponse
from app.schemas.mcp_servers import (
    KiteMcpServerConfigResponse,
    KiteMcpServerConfigUpdateRequest,
    McpJsonConfigResponse,
    McpJsonConfigUpdateRequest,
    McpServerCard,
    McpServerConfig,
    McpServersSummaryResponse,
    McpToolCallRequest,
    McpToolCallResponse,
    McpToolsListResponse,
    McpTransport,
)
from app.services.ai_trading_manager.ai_settings_config import (
    apply_ai_settings_update,
    get_ai_settings_with_source,
    set_ai_settings,
)
from app.services.mcp.mcp_settings_store import (
    get_mcp_settings_with_source,
    normalize_mcp_settings,
    set_mcp_settings,
)
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _corr() -> str:
    return uuid4().hex


def _server_label(server_id: str, cfg: McpServerConfig | None) -> str:
    if cfg and cfg.label:
        return str(cfg.label)
    if server_id == "kite":
        return "Kite MCP"
    if server_id == "tavily":
        return "Tavily MCP (placeholder)"
    return server_id


def _kite_card(cfg) -> McpServerCard:
    kite = cfg.kite_mcp
    enabled = bool(cfg.feature_flags.kite_mcp_enabled)
    configured = bool((kite.server_url or "").strip())
    return McpServerCard(
        id="kite",
        label="Kite MCP",
        enabled=enabled,
        transport="sse",
        configured=configured,
        status=kite.last_status or KiteMcpStatus.unknown,
        last_checked_ts=kite.last_checked_ts,
        last_error=kite.last_error,
        authorized=None,
        tools_available_count=kite.tools_available_count,
    )


def _generic_card(server_id: str, scfg: McpServerConfig) -> McpServerCard:
    transport = scfg.transport.value if hasattr(scfg.transport, "value") else str(scfg.transport)
    configured = False
    if scfg.transport == McpTransport.sse:
        configured = bool((scfg.url or "").strip())
    elif scfg.transport == McpTransport.stdio:
        configured = bool((scfg.command or "").strip())
    return McpServerCard(
        id=server_id,
        label=_server_label(server_id, scfg),
        enabled=bool(scfg.enabled),
        transport=transport,
        configured=configured,
        status=scfg.last_status or KiteMcpStatus.unknown,
        last_checked_ts=scfg.last_checked_ts,
        last_error=scfg.last_error,
        authorized=None,
        tools_available_count=None,
    )


@router.get("/servers", response_model=McpServersSummaryResponse)
def list_mcp_servers(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpServersSummaryResponse:
    ai_cfg, _src = get_ai_settings_with_source(db, settings)
    mcp_cfg, _mcp_src = get_mcp_settings_with_source(db, settings)

    servers = [_kite_card(ai_cfg)]
    for sid, scfg in sorted((mcp_cfg.servers or {}).items(), key=lambda x: x[0]):
        if sid == "kite":
            continue
        servers.append(_generic_card(sid, scfg))

    return McpServersSummaryResponse(
        monitoring_enabled=bool(ai_cfg.feature_flags.monitoring_enabled),
        servers=servers,
    )


@router.get("/config", response_model=McpJsonConfigResponse)
def read_mcp_json_config(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpJsonConfigResponse:
    ai_cfg, _src = get_ai_settings_with_source(db, settings)
    mcp_cfg, _mcp_src = get_mcp_settings_with_source(db, settings)

    servers: Dict[str, Any] = {}
    servers["kite"] = {
        "transport": "sse",
        "url": ai_cfg.kite_mcp.server_url,
        "enabled": bool(ai_cfg.feature_flags.kite_mcp_enabled),
        "auth_method": ai_cfg.kite_mcp.auth_method,
        "auth_profile_ref": ai_cfg.kite_mcp.auth_profile_ref,
        "scopes": ai_cfg.kite_mcp.scopes.model_dump(mode="json"),
        "broker_adapter": ai_cfg.kite_mcp.broker_adapter,
    }

    for sid, scfg in sorted((mcp_cfg.servers or {}).items(), key=lambda x: x[0]):
        if sid == "kite":
            continue
        servers[sid] = scfg.model_dump(mode="json")

    return McpJsonConfigResponse(config={"mcpServers": servers})


def _extract_server_map(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # LM Studio: {"mcpServers": {...}}
    if isinstance(cfg.get("mcpServers"), dict):
        return cfg["mcpServers"]  # type: ignore[return-value]
    # VS Code: {"servers": {...}}
    if isinstance(cfg.get("servers"), dict):
        m: Dict[str, Any] = {}
        for sid, row in cfg["servers"].items():  # type: ignore[union-attr]
            if not isinstance(row, dict):
                continue
            m[str(sid)] = {
                "transport": "sse",
                "url": row.get("url"),
                # VS Code config doesn't have enabled; default on.
                "enabled": True,
            }
        return m
    return {}


@router.put("/config", response_model=McpJsonConfigResponse)
def update_mcp_json_config(
    payload: McpJsonConfigUpdateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpJsonConfigResponse:
    raw = payload.config if isinstance(payload.config, dict) else {}
    server_map = _extract_server_map(raw)
    if not server_map:
        raise HTTPException(status_code=400, detail="Invalid config: expected mcpServers or servers object.")

    ai_cfg, _src = get_ai_settings_with_source(db, settings)
    mcp_cfg, _mcp_src = get_mcp_settings_with_source(db, settings)

    # Apply Kite config (canonical lives in AI settings).
    kite_keys = {"kite", "kite_mcp", "kite-mcp"}
    for sid, scfg_raw in server_map.items():
        if str(sid).strip().lower() in kite_keys:
            if not isinstance(scfg_raw, dict):
                continue
            transport = str(scfg_raw.get("transport") or "sse").strip().lower()
            if transport not in {"sse", "http", "remote"}:
                raise HTTPException(status_code=400, detail="Kite transport must be sse/remote.")
            update = {}
            ff = {}
            kite = {}
            if "enabled" in scfg_raw:
                ff["kite_mcp_enabled"] = bool(scfg_raw.get("enabled"))
            if "url" in scfg_raw:
                kite["server_url"] = scfg_raw.get("url")
            if "auth_method" in scfg_raw:
                kite["auth_method"] = scfg_raw.get("auth_method")
            if "auth_profile_ref" in scfg_raw:
                kite["auth_profile_ref"] = scfg_raw.get("auth_profile_ref")
            if "scopes" in scfg_raw and isinstance(scfg_raw.get("scopes"), dict):
                kite["scopes"] = scfg_raw.get("scopes")
            if "broker_adapter" in scfg_raw:
                kite["broker_adapter"] = scfg_raw.get("broker_adapter")
            if ff:
                update["feature_flags"] = ff
            if kite:
                update["kite_mcp"] = kite

            if update:
                merged = apply_ai_settings_update(existing=ai_cfg, update=AiSettingsUpdate(**update))
                set_ai_settings(db, settings, merged)
                ai_cfg = merged

    # Apply all non-kite servers into MCP settings.
    for sid, scfg_raw in server_map.items():
        sid2 = str(sid).strip()
        if not sid2 or sid2.lower() in kite_keys:
            continue
        if not isinstance(scfg_raw, dict):
            continue
        current = mcp_cfg.servers.get(sid2)
        base = current.model_dump(mode="json") if current else {}
        merged_raw = {**base, **scfg_raw}
        try:
            merged = McpServerConfig.model_validate(merged_raw)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid server config for {sid2}: {exc}") from exc
        # Reset cached state when config changes materially.
        merged.last_status = KiteMcpStatus.unknown
        merged.last_checked_ts = None
        merged.last_error = None
        merged.capabilities_cache = {}
        if not merged.label:
            merged.label = _server_label(sid2, current)
        mcp_cfg.servers[sid2] = merged

    try:
        mcp_cfg = normalize_mcp_settings(mcp_cfg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    set_mcp_settings(db, settings, mcp_cfg)
    record_system_event(
        db,
        level="INFO",
        category="MCP",
        message="MCP JSON config updated.",
        correlation_id=_corr(),
        details={"server_ids": sorted(list(server_map.keys()))},
    )

    return read_mcp_json_config(db=db, settings=settings)


@router.get("/servers/kite/config", response_model=KiteMcpServerConfigResponse)
def read_kite_mcp_server_config(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpServerConfigResponse:
    cfg, _src = get_ai_settings_with_source(db, settings)
    kite = cfg.kite_mcp
    return KiteMcpServerConfigResponse(
        enabled=bool(cfg.feature_flags.kite_mcp_enabled),
        monitoring_enabled=bool(cfg.feature_flags.monitoring_enabled),
        server_url=kite.server_url,
        transport_mode=kite.transport_mode,
        auth_method=kite.auth_method,
        auth_profile_ref=kite.auth_profile_ref,
        scopes=kite.scopes.model_dump(mode="json"),
        broker_adapter=kite.broker_adapter,
        last_status=kite.last_status,
        last_checked_ts=kite.last_checked_ts,
        last_connected_ts=kite.last_connected_ts,
        tools_available_count=kite.tools_available_count,
        last_error=kite.last_error,
        capabilities_cache=kite.capabilities_cache or {},
    )


@router.put("/servers/kite/config", response_model=KiteMcpServerConfigResponse)
def update_kite_mcp_server_config(
    payload: KiteMcpServerConfigUpdateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpServerConfigResponse:
    existing, _src = get_ai_settings_with_source(db, settings)

    ff: Dict[str, Any] = {}
    kite: Dict[str, Any] = {}

    if payload.enabled is not None:
        ff["kite_mcp_enabled"] = bool(payload.enabled)
    if payload.monitoring_enabled is not None:
        ff["monitoring_enabled"] = bool(payload.monitoring_enabled)

    if payload.server_url is not None:
        kite["server_url"] = payload.server_url
    if payload.transport_mode is not None:
        kite["transport_mode"] = payload.transport_mode
    if payload.auth_method is not None:
        kite["auth_method"] = payload.auth_method
    if payload.auth_profile_ref is not None:
        kite["auth_profile_ref"] = payload.auth_profile_ref
    if payload.scopes is not None:
        kite["scopes"] = payload.scopes
    if payload.broker_adapter is not None:
        kite["broker_adapter"] = payload.broker_adapter

    update = {}
    if ff:
        update["feature_flags"] = ff
    if kite:
        update["kite_mcp"] = kite

    if update:
        try:
            merged = apply_ai_settings_update(existing=existing, update=AiSettingsUpdate(**update))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        set_ai_settings(db, settings, merged)
        record_system_event(
            db,
            level="INFO",
            category="KITE_MCP",
            message="Kite MCP server config updated.",
            correlation_id=_corr(),
            details={
                "feature_flags": ff or None,
                "kite_mcp": {k: kite.get(k) for k in sorted(kite.keys())} if kite else None,
            },
        )

    return read_kite_mcp_server_config(db=db, settings=settings)


@router.get("/servers/{server_id}/config", response_model=McpServerConfig)
def read_generic_mcp_server_config(
    server_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpServerConfig:
    sid = (server_id or "").strip()
    if sid.lower() == "kite":
        raise HTTPException(status_code=400, detail="Use /servers/kite/config for Kite.")
    cfg, _src = get_mcp_settings_with_source(db, settings)
    row = cfg.servers.get(sid)
    if row is None:
        # Create a placeholder entry on first read so it becomes editable.
        row = McpServerConfig(label=_server_label(sid, None), enabled=False, transport=McpTransport.sse, url=None)
        cfg.servers[sid] = row
        set_mcp_settings(db, settings, cfg)
    return row


@router.put("/servers/{server_id}/config", response_model=McpServerConfig)
def update_generic_mcp_server_config(
    server_id: str,
    payload: McpServerConfig,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpServerConfig:
    sid = (server_id or "").strip()
    if sid.lower() == "kite":
        raise HTTPException(status_code=400, detail="Use /servers/kite/config for Kite.")
    cfg, _src = get_mcp_settings_with_source(db, settings)

    row = payload
    if not row.label:
        row.label = _server_label(sid, cfg.servers.get(sid))

    try:
        cfg.servers[sid] = row
        cfg = normalize_mcp_settings(cfg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Reset cached status on update.
    cfg.servers[sid].last_status = KiteMcpStatus.unknown
    cfg.servers[sid].last_checked_ts = None
    cfg.servers[sid].last_error = None
    cfg.servers[sid].capabilities_cache = {}

    set_mcp_settings(db, settings, cfg)
    record_system_event(
        db,
        level="INFO",
        category="MCP",
        message="MCP server config updated.",
        correlation_id=_corr(),
        details={"server_id": sid, "transport": str(row.transport), "enabled": bool(row.enabled)},
    )
    return cfg.servers[sid]


@router.get("/servers/kite/status", response_model=KiteMcpStatusResponse)
async def kite_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpStatusResponse:
    # Delegate to the legacy endpoint implementation to preserve semantics.
    return await kite_mcp_api.kite_mcp_status(db=db, settings=settings)


@router.post("/servers/kite/test")
async def kite_test(
    payload: KiteMcpTestRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    # Delegate to AI settings test (it persists status into the AI settings blob).
    return await ai_settings_api.test_kite_mcp_connection(payload=payload, db=db, settings=settings)


@router.post("/servers/{server_id}/test")
async def generic_test(
    server_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sid = (server_id or "").strip()
    if not sid or sid.lower() == "kite":
        raise HTTPException(status_code=400, detail="Invalid server_id.")
    cfg, _src = get_mcp_settings_with_source(db, settings)
    scfg = cfg.servers.get(sid)
    if scfg is None or not scfg.enabled:
        raise HTTPException(status_code=403, detail="Server is disabled.")
    if scfg.transport != McpTransport.sse:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Only SSE transport is supported for non-Kite servers at this time.",
        )
    server_url = (scfg.url or "").strip()
    if not server_url:
        raise HTTPException(status_code=400, detail="Server URL is not configured.")

    checked = datetime.now(UTC)
    cache: Dict[str, Any] = {}
    ok = False
    err: str | None = None
    try:
        async with McpSseClient(server_url=server_url, timeout_seconds=20, endpoint_required=False) as mcp:
            init = await mcp.initialize()
            cache["server_info"] = init.server_info
            cache["capabilities"] = init.capabilities
            tools_res = await mcp.tools_list()
            cache["tools"] = tools_res.get("tools") if isinstance(tools_res, dict) else tools_res
            ok = True
    except (ValueError, McpError) as exc:
        err = str(exc) or "Connection test failed."

    scfg.last_checked_ts = checked
    scfg.last_status = KiteMcpStatus.connected if ok else KiteMcpStatus.error
    scfg.last_error = None if ok else err
    scfg.capabilities_cache = cache if cache else {}
    cfg.servers[sid] = scfg
    set_mcp_settings(db, settings, cfg)

    record_system_event(
        db,
        level="INFO" if ok else "WARNING",
        category="MCP",
        message="MCP server test completed." if ok else "MCP server test failed.",
        correlation_id=_corr(),
        details={
            "server_id": sid,
            "server_url": server_url,
            "status": scfg.last_status.value,
            "checked_ts": checked.isoformat(),
            "error": scfg.last_error,
        },
    )
    return {
        "status": scfg.last_status,
        "checked_ts": checked,
        "error": scfg.last_error,
        "capabilities": scfg.capabilities_cache or {},
    }


@router.post("/servers/kite/auth/start", response_model=KiteMcpAuthStartResponse)
async def kite_auth_start(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpAuthStartResponse:
    return await kite_mcp_api.kite_mcp_auth_start(request=request, db=db, settings=settings)


@router.post("/servers/kite/tools/list", response_model=McpToolsListResponse)
async def kite_tools_list(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpToolsListResponse:
    res = await kite_mcp_api.kite_mcp_tools_list(db=db, settings=settings)
    return McpToolsListResponse(tools=res.tools)


@router.post("/servers/kite/tools/call", response_model=McpToolCallResponse)
async def kite_tools_call(
    payload: McpToolCallRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpToolCallResponse:
    res = await kite_mcp_api.kite_mcp_tools_call(
        payload=kite_mcp_api.KiteMcpToolCallRequest(name=payload.name, arguments=payload.arguments or {}),
        db=db,
        settings=settings,
    )
    return McpToolCallResponse(result=res.result)


@router.post("/servers/{server_id}/tools/list", response_model=McpToolsListResponse)
async def generic_tools_list(
    server_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpToolsListResponse:
    sid = (server_id or "").strip()
    if not sid or sid.lower() == "kite":
        raise HTTPException(status_code=400, detail="Invalid server_id.")
    cfg, _src = get_mcp_settings_with_source(db, settings)
    scfg = cfg.servers.get(sid)
    if scfg is None or not scfg.enabled:
        raise HTTPException(status_code=403, detail="Server is disabled.")
    if scfg.transport != McpTransport.sse:
        raise HTTPException(status_code=501, detail="Only SSE transport is supported for this server.")
    server_url = (scfg.url or "").strip()
    if not server_url:
        raise HTTPException(status_code=400, detail="Server URL is not configured.")

    try:
        async with McpSseClient(server_url=server_url, timeout_seconds=20, endpoint_required=False) as mcp:
            await mcp.initialize()
            tools = await mcp.tools_list()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "tools/list failed.") from exc

    rows = tools.get("tools") if isinstance(tools, dict) else []
    if not isinstance(rows, list):
        rows = []
    return McpToolsListResponse(tools=rows)


@router.post("/servers/{server_id}/tools/call", response_model=McpToolCallResponse)
async def generic_tools_call(
    server_id: str,
    payload: McpToolCallRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> McpToolCallResponse:
    sid = (server_id or "").strip()
    if not sid or sid.lower() == "kite":
        raise HTTPException(status_code=400, detail="Invalid server_id.")
    cfg, _src = get_mcp_settings_with_source(db, settings)
    scfg = cfg.servers.get(sid)
    if scfg is None or not scfg.enabled:
        raise HTTPException(status_code=403, detail="Server is disabled.")
    if scfg.transport != McpTransport.sse:
        raise HTTPException(status_code=501, detail="Only SSE transport is supported for this server.")
    server_url = (scfg.url or "").strip()
    if not server_url:
        raise HTTPException(status_code=400, detail="Server URL is not configured.")

    try:
        async with McpSseClient(server_url=server_url, timeout_seconds=30, endpoint_required=False) as mcp:
            await mcp.initialize()
            res = await mcp.tools_call(name=payload.name, arguments=payload.arguments or {})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "tools/call failed.") from exc

    return McpToolCallResponse(result=res if isinstance(res, dict) else {"result": res})


@router.post("/servers/kite/snapshot/fetch")
async def kite_snapshot_fetch(
    account_id: str = "default",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    # Keep signature compatible with existing frontend usage.
    return await kite_mcp_api.kite_mcp_fetch_snapshot(account_id=account_id, db=db, settings=settings, user=None)


__all__ = ["router"]
