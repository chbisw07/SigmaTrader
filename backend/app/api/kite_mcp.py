from __future__ import annotations

import os
import re
import urllib.parse
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import User
from app.schemas.ai_trading_manager import BrokerSnapshot
from app.schemas.ai_settings import KiteMcpStatus
from app.schemas.kite_mcp import (
    KiteMcpAuthStartResponse,
    KiteMcpStatusResponse,
    KiteMcpToolCallRequest,
    KiteMcpToolCallResponse,
    KiteMcpToolsListResponse,
)
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source, set_ai_settings
from app.services.kite_mcp.legacy_cache import hydrate_legacy_caches_from_kite_mcp_snapshot
from app.services.kite_mcp.secrets import get_auth_session_id, set_auth_session_id, set_request_token
from app.services.kite_mcp.session_manager import kite_mcp_sessions
from app.services.kite_mcp.snapshot import fetch_kite_mcp_snapshot
from app.services.ai_trading_manager.coverage import sync_position_shadows_from_snapshot
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()

_LOGIN_URL_RE = re.compile(r"https://kite\.zerodha\.com/connect/login\?[^\s]+")


def _corr() -> str:
    return uuid4().hex


def _require_kite_mcp_enabled(db: Session, settings: Settings) -> None:
    cfg, _src = get_ai_settings_with_source(db, settings)
    if not cfg.feature_flags.kite_mcp_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kite MCP is disabled. Enable it in Settings → AI.",
        )
    if not cfg.kite_mcp.server_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kite MCP server URL is not configured.",
        )


def _extract_auth_session_id(login_url: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(login_url)
        qs = urllib.parse.parse_qs(parsed.query)
        redirect_params = (qs.get("redirect_params") or [None])[0]
        if not redirect_params:
            return None
        decoded = urllib.parse.unquote_plus(str(redirect_params))
        # redirect_params looks like: session_id=<token>
        parts = urllib.parse.parse_qs(decoded, keep_blank_values=True)
        return (parts.get("session_id") or [None])[0]
    except Exception:
        return None


def _infer_backend_base_url(request: Request, settings: Settings) -> str:
    # Config wins (works behind reverse proxies / tunnels).
    if getattr(settings, "backend_base_url", None):
        return str(settings.backend_base_url).rstrip("/")

    # Otherwise infer from request headers.
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[
        0
    ].strip()
    return f"{proto}://{host}".rstrip("/")


def _rewrite_login_url(login_url: str, *, redirect_uri: str) -> str:
    """Best-effort rewrite to force callback to SigmaTrader.

    NOTE: Kite MCP uses the `kitemcp` app key. Whether Zerodha honors a dynamic
    redirect URI is not guaranteed; we inject it as both a top-level query
    param and within redirect_params for maximum compatibility.
    """

    try:
        p = urllib.parse.urlparse(login_url)
        qs = urllib.parse.parse_qs(p.query, keep_blank_values=True)

        # Add top-level redirect_uri.
        qs["redirect_uri"] = [redirect_uri]

        # Also inject into redirect_params if present.
        rp = (qs.get("redirect_params") or [None])[0]
        if rp:
            decoded = urllib.parse.unquote_plus(str(rp))
            parts = urllib.parse.parse_qs(decoded, keep_blank_values=True)
            parts["redirect_uri"] = [redirect_uri]
            # IMPORTANT: Avoid double-encoding. Store redirect_params as a raw
            # querystring; the outer urlencode will encode it exactly once.
            sid = (parts.get("session_id") or [None])[0]
            if sid:
                qs["redirect_params"] = [f"session_id={sid}&redirect_uri={redirect_uri}"]

        query2 = urllib.parse.urlencode({k: (v[0] if isinstance(v, list) and v else v) for k, v in qs.items()})
        return urllib.parse.urlunparse(p._replace(query=query2))
    except Exception:
        return login_url


async def _is_authorized(session, *, probe_tool: str = "get_profile") -> bool:
    try:
        res = await session.tools_call(name=probe_tool, arguments={})
    except Exception:
        return False
    # Tool responses follow MCP tool/call result shape.
    if isinstance(res, dict) and res.get("isError") is True:
        return False
    return True


@router.get("/status", response_model=KiteMcpStatusResponse)
async def kite_mcp_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpStatusResponse:
    cfg, _src = get_ai_settings_with_source(db, settings)
    server_url = cfg.kite_mcp.server_url
    if not cfg.feature_flags.kite_mcp_enabled or not server_url:
        return KiteMcpStatusResponse(server_url=server_url, connected=False, authorized=False)

    auth_sid = get_auth_session_id(db, settings)
    session = await kite_mcp_sessions.get_session(server_url=server_url, auth_session_id=auth_sid)
    connected = False
    last_error: str | None = None
    tools_count: int | None = None
    last_connected_at: datetime | None = None
    try:
        await session.ensure_initialized()
        connected = True
        last_connected_at = datetime.now(UTC)
    except Exception as exc:
        last_error = str(exc) or "Failed to connect."
        cfg.kite_mcp.last_error = last_error
        cfg.kite_mcp.last_status = KiteMcpStatus.error
        set_ai_settings(db, settings, cfg)
        return KiteMcpStatusResponse(
            server_url=server_url,
            connected=False,
            authorized=False,
            last_error=last_error,
        )

    authorized = await _is_authorized(session)
    try:
        tools = await session.tools_list()
        rows = tools.get("tools") if isinstance(tools, dict) else []
        tools_count = len(rows) if isinstance(rows, list) else None
    except Exception as exc:
        last_error = str(exc) or "tools/list failed."

    # Persist last-known status (best-effort) so the UI can show state even
    # without running the explicit Test Connection action.
    cfg.kite_mcp.last_connected_ts = last_connected_at
    cfg.kite_mcp.tools_available_count = tools_count
    cfg.kite_mcp.last_status = KiteMcpStatus.connected if connected else cfg.kite_mcp.last_status
    cfg.kite_mcp.last_error = last_error
    set_ai_settings(db, settings, cfg)

    return KiteMcpStatusResponse(
        server_url=server_url,
        connected=connected,
        authorized=authorized,
        last_connected_at=last_connected_at,
        tools_available_count=tools_count,
        server_info=session.state.server_info or {},
        capabilities=session.state.capabilities or {},
        last_error=last_error,
    )


@router.get("/auth/start", response_model=KiteMcpAuthStartResponse)
async def kite_mcp_auth_start(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpAuthStartResponse:
    _require_kite_mcp_enabled(db, settings)
    cfg, _src = get_ai_settings_with_source(db, settings)
    assert cfg.kite_mcp.server_url

    auth_sid = get_auth_session_id(db, settings)
    session = await kite_mcp_sessions.get_session(server_url=cfg.kite_mcp.server_url, auth_session_id=auth_sid)
    try:
        await session.ensure_initialized()
        res = await session.tools_call(name="login", arguments={})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Login tool failed.") from exc

    content = res.get("content") if isinstance(res, dict) else None
    text = ""
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = str(content[0].get("text") or "")
    m = _LOGIN_URL_RE.search(text or "")
    if not m:
        raise HTTPException(status_code=502, detail="Kite MCP login link not found in response.")
    raw_login_url = m.group(0)

    # NOTE: Kite MCP's `kitemcp` app may not honor dynamic redirect_uri. We
    # keep this behind an explicit env flag because rewriting redirect_params
    # can break the upstream callback.
    redirect_uri: str | None = None
    login_url = raw_login_url
    if str(os.getenv("ST_KITE_MCP_FORCE_REDIRECT_URI") or "").strip().lower() in {"1", "true", "yes", "on"}:
        base = _infer_backend_base_url(request, settings)
        redirect_uri = f"{base}/api/mcp/kite/auth/callback"
        login_url = _rewrite_login_url(raw_login_url, redirect_uri=redirect_uri)

    # Extract and store auth session id (best-effort).
    extracted = _extract_auth_session_id(login_url)
    if extracted:
        try:
            set_auth_session_id(db, settings, extracted)
        except Exception:
            pass

    record_system_event(
        db,
        level="INFO",
        category="KITE_MCP",
        message="Kite MCP auth started.",
        correlation_id=_corr(),
        details={
            "event_type": "KITE_MCP_AUTH_START",
            "server_url": cfg.kite_mcp.server_url,
            "redirect_uri": redirect_uri,
        },
    )

    # Also update AI settings status to reflect auth flow started.
    cfg.kite_mcp.last_error = None
    set_ai_settings(db, settings, cfg)

    return KiteMcpAuthStartResponse(warning_text=text.strip(), login_url=login_url)


@router.get("/auth/callback", include_in_schema=False)
async def kite_mcp_auth_callback(
    session_id: str | None = None,
    sessionId: str | None = None,  # noqa: N803 - upstream naming
    code: str | None = None,
    request_token: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Optional OAuth callback endpoint.

    The current Kite MCP login flow typically completes via Kite's own redirect,
    but we keep this endpoint so deployments can choose to route callbacks back
    into SigmaTrader (e.g., when the MCP server supports custom redirect URLs).
    """

    sid = (session_id or sessionId or "").strip() or None
    rt = (request_token or code or "").strip() or None

    if not sid or not rt:
        record_system_event(
            db,
            level="WARNING",
            category="KITE_MCP",
            message="Kite MCP auth callback missing required parameters.",
            correlation_id=_corr(),
            details={
                "event_type": "KITE_MCP_AUTH_CALLBACK",
                "has_session_id": bool(sid),
                "has_request_token": bool(rt),
                "status": status,
            },
        )
        html = """
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Kite MCP Auth</title></head>
  <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 24px;">
    <h2>Kite MCP authorization failed</h2>
    <p>Missing required parameters (session_id and/or request_token).</p>
    <p>Close this tab and retry Authorization from SigmaTrader → Settings → AI.</p>
  </body>
</html>
""".strip()
        return HTMLResponse(content=html, status_code=400)

    stored = False
    try:
        set_auth_session_id(db, settings, sid)
        set_request_token(db, settings, rt)
        stored = True
    except Exception:
        stored = False

    record_system_event(
        db,
        level="INFO",
        category="KITE_MCP",
        message="Kite MCP auth callback received.",
        correlation_id=_corr(),
        details={
            "event_type": "KITE_MCP_AUTH_CALLBACK",
            "stored": stored,
            "status": status,
            "has_session_id": True,
            "has_request_token": True,
        },
    )

    # Best-effort verify session by reconnecting and listing tools.
    try:
        await kite_mcp_sessions.reset()
        cfg, _src = get_ai_settings_with_source(db, settings)
        if cfg.feature_flags.kite_mcp_enabled and cfg.kite_mcp.server_url:
            session = await kite_mcp_sessions.get_session(server_url=cfg.kite_mcp.server_url, auth_session_id=sid)
            await session.ensure_initialized()
            tools = await session.tools_list()
            rows = tools.get("tools") if isinstance(tools, dict) else []
            tools_count = len(rows) if isinstance(rows, list) else None
            cfg.kite_mcp.last_status = KiteMcpStatus.connected
            cfg.kite_mcp.last_error = None
            cfg.kite_mcp.last_connected_ts = datetime.now(UTC)
            cfg.kite_mcp.tools_available_count = tools_count
            set_ai_settings(db, settings, cfg)
            record_system_event(
                db,
                level="INFO",
                category="KITE_MCP",
                message="Kite MCP session verified after callback.",
                correlation_id=_corr(),
                details={"event_type": "KITE_MCP_SESSION_VERIFIED", "tools_count": tools_count},
            )
    except Exception as exc:
        record_system_event(
            db,
            level="WARNING",
            category="KITE_MCP",
            message="Kite MCP session verification failed after callback.",
            correlation_id=_corr(),
            details={"event_type": "KITE_MCP_SESSION_VERIFY_FAILED", "error": str(exc) or "unknown"},
        )

    # Redirect back to the UI.
    return RedirectResponse(url="/settings?tab=ai&kite=connected", status_code=303)


#
# Tools endpoints and the MCP console UI are added in follow-up commits:
# - POST /tools/list
# - POST /tools/call


@router.post("/tools/list", response_model=KiteMcpToolsListResponse)
async def kite_mcp_tools_list(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpToolsListResponse:
    _require_kite_mcp_enabled(db, settings)
    cfg, _src = get_ai_settings_with_source(db, settings)
    assert cfg.kite_mcp.server_url

    auth_sid = get_auth_session_id(db, settings)
    session = await kite_mcp_sessions.get_session(server_url=cfg.kite_mcp.server_url, auth_session_id=auth_sid)
    try:
        tools = await session.tools_list()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "tools/list failed.") from exc

    rows = tools.get("tools") if isinstance(tools, dict) else []
    if not isinstance(rows, list):
        rows = []

    record_system_event(
        db,
        level="INFO",
        category="KITE_MCP",
        message="Kite MCP tools listed.",
        correlation_id=_corr(),
        details={"event_type": "KITE_MCP_TOOLS_LIST", "count": len(rows)},
    )
    return KiteMcpToolsListResponse(tools=rows)


@router.post("/tools/call", response_model=KiteMcpToolCallResponse)
async def kite_mcp_tools_call(
    payload: KiteMcpToolCallRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KiteMcpToolCallResponse:
    _require_kite_mcp_enabled(db, settings)
    cfg, _src = get_ai_settings_with_source(db, settings)
    assert cfg.kite_mcp.server_url

    auth_sid = get_auth_session_id(db, settings)
    session = await kite_mcp_sessions.get_session(server_url=cfg.kite_mcp.server_url, auth_session_id=auth_sid)
    try:
        res = await session.tools_call(name=payload.name, arguments=payload.arguments or {})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "tools/call failed.") from exc

    record_system_event(
        db,
        level="INFO",
        category="KITE_MCP",
        message="Kite MCP tool called.",
        correlation_id=_corr(),
        details={
            "event_type": "KITE_MCP_TOOL_CALL",
            "tool": payload.name,
            "args_keys": sorted(list((payload.arguments or {}).keys())),
            "is_error": bool(res.get("isError")) if isinstance(res, dict) else None,
        },
    )
    return KiteMcpToolCallResponse(result=res if isinstance(res, dict) else {"result": res})


@router.post("/snapshot/fetch", response_model=BrokerSnapshot)
async def kite_mcp_fetch_snapshot(
    account_id: str = "default",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> BrokerSnapshot:
    _require_kite_mcp_enabled(db, settings)
    snap = await fetch_kite_mcp_snapshot(db, settings, account_id=account_id)
    audit_store.persist_broker_snapshot(db, snap, user_id=None)
    try:
        sync_position_shadows_from_snapshot(db, settings, snapshot=snap, user_id=user.id if user else None)
    except Exception:
        # Coverage sync must never block snapshot fetch.
        pass
    legacy = hydrate_legacy_caches_from_kite_mcp_snapshot(db, snapshot=snap, user=user)
    record_system_event(
        db,
        level="INFO",
        category="KITE_MCP",
        message="Kite MCP snapshot fetched.",
        correlation_id=_corr(),
        details={
            "event_type": "KITE_MCP_SNAPSHOT_FETCH",
            "account_id": account_id,
            "holdings": len(snap.holdings),
            "positions": len(snap.positions),
            "orders": len(snap.orders),
            "legacy_cache": legacy,
        },
    )
    return snap


__all__ = ["router"]
