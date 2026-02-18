from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SchedulerState:
    running: bool = False
    last_tick_at: datetime | None = None


_state = SchedulerState()


def _loop() -> None:
    settings = get_settings()
    if not settings.monitoring_enabled:
        return

    logger.info(
        "AI TM monitoring scheduler started",
        extra={"extra": {"monitoring_enabled": True}},
    )
    _state.running = True
    try:
        while get_settings().monitoring_enabled:
            _state.last_tick_at = datetime.now(UTC)
            # Phase 0: store + API only. Evaluation/triggering arrives in Phase 1.
            time.sleep(1.0)
    finally:
        _state.running = False
        logger.info("AI TM monitoring scheduler stopped")


def schedule_ai_tm_monitoring() -> None:
    settings = get_settings()
    if not settings.monitoring_enabled:
        return
    if _state.running:
        return
    t = threading.Thread(target=_loop, name="ai-tm-monitoring", daemon=True)
    t.start()


def get_scheduler_state() -> SchedulerState:
    return _state

