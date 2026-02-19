from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import log_with_correlation
from app.db.session import get_db
from app.schemas.ai_chat import AiChatRequest, AiChatResponse, AiToolCallRow
from app.schemas.ai_trading_manager import AiTmMessage, AiTmMessageRole
from app.services.ai_toolcalling.orchestrator import run_chat
from app.services.ai_trading_manager import audit_store

# ruff: noqa: B008  # FastAPI dependency injection pattern

logger = logging.getLogger(__name__)
router = APIRouter()


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or request.headers.get("X-Request-ID") or uuid4().hex


@router.post("/chat", response_model=AiChatResponse)
async def ai_chat(
    payload: AiChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AiChatResponse:
    corr = _correlation_id(request)
    log_with_correlation(logger, request, logging.INFO, "ai.chat.requested", account_id=payload.account_id)

    auth_message_id = uuid4().hex
    result = await run_chat(
        db,
        settings,
        account_id=payload.account_id,
        user_message=payload.message,
        authorization_message_id=auth_message_id,
        ui_context=payload.context or {},
        correlation_id=corr,
    )

    # Persist chat messages to the same assistant thread for continuity in UI.
    user_msg = AiTmMessage(
        message_id=auth_message_id,
        role=AiTmMessageRole.user,
        content=payload.message,
        created_at=datetime.now(UTC),
        correlation_id=corr,
    )
    assistant_msg = AiTmMessage(
        message_id=uuid4().hex,
        role=AiTmMessageRole.assistant,
        content=result.assistant_message,
        created_at=datetime.now(UTC),
        correlation_id=corr,
        decision_id=result.decision_id,
    )
    audit_store.append_chat_messages(
        db,
        user_id=None,
        account_id=payload.account_id,
        thread_id="default",
        messages=[user_msg, assistant_msg],
    )
    thread = audit_store.get_thread(db, account_id=payload.account_id, thread_id="default")

    return AiChatResponse(
        assistant_message=result.assistant_message,
        decision_id=result.decision_id,
        tool_calls=[
            AiToolCallRow(
                name=t.name,
                arguments=t.arguments,
                status=t.status,
                duration_ms=t.duration_ms,
                result_preview=t.result_preview,
                error=t.error,
            )
            for t in result.tool_calls
        ],
        thread=thread,
    )


__all__ = ["router"]
