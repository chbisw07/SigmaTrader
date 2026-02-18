from __future__ import annotations

import re
import urllib.parse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.ai_trading_manager import BrokerSnapshot
from app.schemas.kite_mcp import (
    KiteMcpAuthStartResponse,
    KiteMcpStatusResponse,
    KiteMcpToolCallRequest,
    KiteMcpToolCallResponse,
    KiteMcpToolsListResponse,
)
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source, set_ai_settings
from app.services.kite_mcp.secrets import get_auth_session_id, set_auth_session_id
from app.services.kite_mcp.session_manager import kite_mcp_sessions
from app.services.kite_mcp.snapshot import fetch_kite_mcp_snapshot
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
    try:
        await session.ensure_initialized()
        connected = True
    except Exception as exc:
        last_error = str(exc) or "Failed to connect."
        return KiteMcpStatusResponse(
            server_url=server_url,
            connected=False,
            authorized=False,
            last_error=last_error,
        )

    authorized = await _is_authorized(session)
    return KiteMcpStatusResponse(
        server_url=server_url,
        connected=connected,
        authorized=authorized,
        server_info=session.state.server_info or {},
        capabilities=session.state.capabilities or {},
        last_error=last_error,
    )


@router.get("/auth/start", response_model=KiteMcpAuthStartResponse)
async def kite_mcp_auth_start(
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
    login_url = m.group(0)

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
        },
    )

    # Also update AI settings status to reflect auth flow started.
    cfg.kite_mcp.last_error = None
    set_ai_settings(db, settings, cfg)

    return KiteMcpAuthStartResponse(warning_text=text.strip(), login_url=login_url)


@router.get("/auth/callback", include_in_schema=False)
def kite_mcp_auth_callback(
    session_id: str | None = None,
    sessionId: str | None = None,  # noqa: N803 - upstream naming
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Optional OAuth callback endpoint.

    The current Kite MCP login flow typically completes via Kite's own redirect,
    but we keep this endpoint so deployments can choose to route callbacks back
    into SigmaTrader (e.g., when the MCP server supports custom redirect URLs).
    """

    stored = False
    sid = (session_id or sessionId or "").strip() or None
    if sid:
        try:
            set_auth_session_id(db, settings, sid)
            stored = True
        except Exception:
            stored = False

    record_system_event(
        db,
        level="INFO",
        category="KITE_MCP",
        message="Kite MCP auth callback received.",
        correlation_id=_corr(),
        details={"event_type": "KITE_MCP_AUTH_CALLBACK", "stored": stored},
    )

    html = """
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Kite MCP Auth</title></head>
  <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 24px;">
    <h2>Kite MCP authorization received</h2>
    <p>You can close this tab and return to SigmaTrader → Settings → AI, then click “Refresh status”.</p>
  </body>
</html>
""".strip()
    return HTMLResponse(content=html)


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
) -> BrokerSnapshot:
    _require_kite_mcp_enabled(db, settings)
    snap = await fetch_kite_mcp_snapshot(db, settings, account_id=account_id)
    audit_store.persist_broker_snapshot(db, snap, user_id=None)
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
        },
    )
    return snap


__all__ = ["router"]
