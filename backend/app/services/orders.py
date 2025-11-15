from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Alert, Order


def create_order_from_alert(
    db: Session, alert: Alert, *, mode: str = "MANUAL"
) -> Order:
    """Create and persist an Order in WAITING state derived from an Alert.

    This is intentionally simple for Sprint S03 / G02:
    - Uses alert qty/price as-is.
    - Defaults to MARKET/MIS and MANUAL mode.
    - No risk checks or execution routing yet.
    """

    qty = alert.qty if alert.qty is not None else 0.0

    order = Order(
        alert_id=alert.id,
        strategy_id=alert.strategy_id,
        symbol=alert.symbol,
        exchange=alert.exchange,
        side=alert.action,
        qty=qty,
        price=alert.price,
        order_type="MARKET",
        product="MIS",
        gtt=False,
        status="WAITING",
        mode=mode,
        simulated=False,
    )

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


__all__ = ["create_order_from_alert"]
