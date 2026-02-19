from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.ai_trading_manager import AiTmThread


class AiChatAttachment(BaseModel):
    file_id: str
    how: str = "auto"


class AiChatRequest(BaseModel):
    account_id: str = "default"
    message: str = Field(min_length=1, max_length=10_000)
    context: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[AiChatAttachment] = Field(default_factory=list)
    ui_context: Optional[Dict[str, Any]] = None


class AiToolCallRow(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    status: str
    duration_ms: int
    result_preview: str
    error: Optional[str] = None


class AiChatResponse(BaseModel):
    assistant_message: str
    decision_id: str
    tool_calls: List[AiToolCallRow] = Field(default_factory=list)
    render_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    attachments_used: List[Dict[str, Any]] = Field(default_factory=list)
    thread: Optional[AiTmThread] = None


__all__ = ["AiChatAttachment", "AiChatRequest", "AiChatResponse", "AiToolCallRow"]
