from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.core.logging import log_with_correlation
from app.db.session import get_db
from app.schemas.ai_chat import AiChatRequest, AiChatResponse, AiToolCallRow
from app.schemas.ai_trading_manager import AiTmAttachmentRef, AiTmMessage, AiTmMessageRole
from app.services.ai.active_config import get_active_config
from app.services.ai.files_store import get_file_meta
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
    user=Depends(get_current_user_optional),
) -> AiChatResponse:
    corr = _correlation_id(request)
    log_with_correlation(logger, request, logging.INFO, "ai.chat.requested", account_id=payload.account_id)

    # Resolve attachment metadata (and enforce access control).
    ai_cfg, _ai_src = get_active_config(db, settings)
    include_preview_rows = not bool(ai_cfg.do_not_send_pii)
    attachments_for_llm: list[dict[str, object]] = []
    attachments_for_thread: list[AiTmAttachmentRef] = []
    if payload.attachments:
        if user is None:
            raise HTTPException(status_code=400, detail="Attachments require a logged-in session.")
        for a in payload.attachments:
            meta = get_file_meta(db, file_id=a.file_id, user_id=int(user.id))
            if meta is None:
                raise HTTPException(status_code=404, detail=f"Attachment not found: {a.file_id}")
            # For remote providers, only include summaries (no raw file contents).
            # In PII-safe mode, omit preview rows from the LLM payload.
            attachments_for_llm.append(
                {
                    "file_id": meta.file_id,
                    "filename": meta.filename,
                    "size": meta.size,
                    "mime": meta.mime,
                    "summary": {
                        "kind": meta.summary.kind,
                        "columns": meta.summary.columns,
                        "row_count": meta.summary.row_count,
                        "preview_rows": meta.summary.preview_rows if include_preview_rows else [],
                        "sheets": meta.summary.sheets,
                        "active_sheet": meta.summary.active_sheet,
                    },
                }
            )
            attachments_for_thread.append(
                AiTmAttachmentRef(
                    file_id=meta.file_id,
                    filename=meta.filename,
                    size=meta.size,
                    mime=meta.mime,
                )
            )

    auth_message_id = uuid4().hex
    result = await run_chat(
        db,
        settings,
        account_id=payload.account_id,
        user_message=payload.message,
        authorization_message_id=auth_message_id,
        attachments=attachments_for_llm,
        ui_context=payload.ui_context or payload.context or {},
        correlation_id=corr,
    )

    # Persist chat messages to the same assistant thread for continuity in UI.
    user_msg = AiTmMessage(
        message_id=auth_message_id,
        role=AiTmMessageRole.user,
        content=payload.message,
        created_at=datetime.now(UTC),
        correlation_id=corr,
        attachments=attachments_for_thread,
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
        render_blocks=[],
        attachments_used=[
            {"file_id": a.file_id, "summary_used": True} for a in (payload.attachments or [])
        ],
        thread=thread,
    )


__all__ = ["router"]
