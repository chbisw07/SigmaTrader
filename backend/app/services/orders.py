from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Alert, Order
from app.services.price_ticks import round_price_to_tick


def requeue_order_to_waiting(
    db: Session,
    *,
    source: Order,
    reason: str | None = None,
) -> Order:
    """Create a new manual WAITING order cloned from an existing order.

    Notes:
    - client_order_id is intentionally cleared so webhook idempotency remains
      anchored on the original row.
    - Broker ids are cleared so the queued order is always "not yet sent".
    """

    base_reason = (reason or "").strip()
    if not base_reason:
        base_reason = f"Requeued from order #{int(source.id)}."

    msg = base_reason
    if (source.error_message or "").strip():
        msg = f"{msg} Original: {str(source.error_message).strip()}"

    queue_order = Order(
        user_id=source.user_id,
        alert_id=source.alert_id,
        strategy_id=source.strategy_id,
        portfolio_group_id=getattr(source, "portfolio_group_id", None),
        deployment_id=getattr(source, "deployment_id", None),
        deployment_action_id=getattr(source, "deployment_action_id", None),
        client_order_id=None,
        symbol=source.symbol,
        exchange=source.exchange,
        side=source.side,
        qty=source.qty,
        price=source.price,
        order_type=source.order_type,
        trigger_price=source.trigger_price,
        trigger_percent=source.trigger_percent,
        product=source.product,
        gtt=source.gtt,
        synthetic_gtt=source.synthetic_gtt,
        trigger_operator=source.trigger_operator,
        armed_at=None,
        last_checked_at=None,
        last_seen_price=None,
        triggered_at=None,
        status="WAITING",
        mode="MANUAL",
        execution_target=getattr(source, "execution_target", None) or "LIVE",
        broker_name=getattr(source, "broker_name", None) or "zerodha",
        broker_order_id=None,
        zerodha_order_id=None,
        broker_account_id=getattr(source, "broker_account_id", None),
        error_message=msg,
        simulated=False,
        risk_spec_json=getattr(source, "risk_spec_json", None),
        is_exit=bool(getattr(source, "is_exit", False)),
    )
    db.add(queue_order)
    db.commit()
    db.refresh(queue_order)
    return queue_order


def create_order_from_alert(
    db: Session,
    alert: Alert,
    *,
    mode: str = "MANUAL",
    product: str = "MIS",
    order_type: str = "MARKET",
    broker_name: str | None = None,
    execution_target: str | None = None,
    user_id: int | None = None,
    client_order_id: str | None = None,
    risk_spec_json: str | None = None,
    is_exit: bool = False,
) -> Order:
    """Create and persist an Order in WAITING state derived from an Alert.

    This is intentionally simple for Sprint S03 / G02:
    - Uses alert qty/price as-is.
    - Defaults to MARKET/MIS and MANUAL mode unless overridden.
    - No risk checks or execution routing yet.
    """

    qty = alert.qty if alert.qty is not None else 0.0

    order_price = round_price_to_tick(alert.price) if order_type != "MARKET" else None

    order = Order(
        alert_id=alert.id,
        strategy_id=alert.strategy_id,
        user_id=user_id,
        client_order_id=(str(client_order_id).strip() if client_order_id else None),
        symbol=alert.symbol,
        exchange=alert.exchange,
        side=alert.action,
        qty=qty,
        price=order_price,
        order_type=order_type,
        product=product,
        gtt=False,
        status="WAITING",
        mode=mode,
        broker_name=(broker_name or "zerodha").strip().lower() or "zerodha",
        execution_target=(execution_target or "LIVE").strip().upper() or "LIVE",
        simulated=False,
        risk_spec_json=risk_spec_json,
        is_exit=bool(is_exit),
    )

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


__all__ = ["create_order_from_alert", "requeue_order_to_waiting"]
