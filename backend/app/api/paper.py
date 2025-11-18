from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import User
from app.services.paper_trading import PaperFillResult, poll_paper_orders

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class PaperPollResponse(BaseModel):
    filled_orders: int


@router.post("/poll", response_model=PaperPollResponse)
def run_paper_poll(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, int]:
    """Run a single paper-trading fill pass.

    This endpoint is intended to be called periodically (e.g. via cron)
    at the desired paper-trading poll interval.
    """

    # For now any authenticated user can trigger a poll; the function
    # itself only operates on simulated orders for strategies configured
    # with execution_target='PAPER'.
    result: PaperFillResult = poll_paper_orders(db, settings)
    return {"filled_orders": result.filled_orders}


__all__ = ["router"]
