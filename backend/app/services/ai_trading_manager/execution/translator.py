from __future__ import annotations

from typing import List

from app.schemas.ai_trading_manager import TradePlan

from ..broker_adapter import OrderIntent


def translate_plan_to_order_intents(*, plan: TradePlan, correlation_id: str) -> List[OrderIntent]:
    # Phase 0: minimal deterministic translation (one intent per symbol).
    qty_raw = plan.intent.constraints.get("qty", 1)
    try:
        qty = float(qty_raw)
    except Exception:
        qty = 1.0
    qty = max(qty, 0.0)

    intents: List[OrderIntent] = []
    for sym in sorted({s.upper() for s in plan.intent.symbols}):
        intents.append(
            OrderIntent(
                symbol=sym,
                side=plan.intent.side,
                qty=qty,
                product=plan.intent.product,
                order_type=str(plan.order_skeleton.get("order_type") or "MARKET").upper(),
                limit_price=None,
                correlation_id=correlation_id,
            )
        )
    return intents

