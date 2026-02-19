from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import List

from app.schemas.ai_trading_manager import TradePlan

IST_OFFSET = timedelta(hours=5, minutes=30)
DEFAULT_MARKET_OPEN = time(9, 15)
DEFAULT_MARKET_CLOSE = time(15, 30)


def _to_ist_naive(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (ts.astimezone(UTC) + IST_OFFSET).replace(tzinfo=None)


def evaluate_market_hours(*, plan: TradePlan, eval_ts: datetime) -> List[dict]:
    now_ist = _to_ist_naive(eval_ts)
    minutes = now_ist.hour * 60 + now_ist.minute
    start = DEFAULT_MARKET_OPEN.hour * 60 + DEFAULT_MARKET_OPEN.minute
    end = DEFAULT_MARKET_CLOSE.hour * 60 + DEFAULT_MARKET_CLOSE.minute
    if not (start <= minutes <= end):
        return [{"code": "MARKET_CLOSED", "message": "Market is closed.", "details": {}}]
    # MIS has stricter constraints later; Phase 0 keeps a simple guardrail.
    if plan.intent.product == "MIS":
        # Prevent MIS orders too close to close in Phase 0 (coarse).
        if minutes > (end - 5):
            return [
                {
                    "code": "MIS_TOO_CLOSE_TO_CLOSE",
                    "message": "MIS order too close to market close.",
                    "details": {},
                }
            ]
    return []
