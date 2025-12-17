from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET, is_market_open_now
from app.db.session import SessionLocal
from app.models import AlertDefinition, AlertEvent, Group, GroupMember, User
from app.schemas.positions import HoldingRead
from app.services.alerts_v3_compiler import (
    CustomIndicatorMap,
    compile_alert_definition,
    compile_custom_indicators_for_user,
)
from app.services.alerts_v3_expression import (
    BinaryNode,
    CallNode,
    ComparisonNode,
    EventNode,
    ExprNode,
    IdentNode,
    LogicalNode,
    NotNode,
    UnaryNode,
    eval_condition,
    loads_ast,
    timeframe_to_timedelta,
)
from app.services.indicator_alerts import IndicatorAlertError


class AlertsV3Error(RuntimeError):
    """Raised when v3 alert evaluation cannot be completed."""


_scheduler_started = False
_scheduler_stop_event = Event()


def _now_ist_naive() -> datetime:
    return (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)


_HOLDINGS_SNAPSHOT_METRICS = {
    # These are expected by users to match the live Holdings page
    # (Zerodha snapshot), not just cached positions + daily candles.
    "TODAY_PNL_PCT",
    "PNL_PCT",
    "CURRENT_VALUE",
    "INVESTED",
    "QTY",
    "AVG_PRICE",
}


def _iter_nodes(expr: ExprNode) -> Iterable[ExprNode]:
    yield expr
    if isinstance(expr, (IdentNode,)):
        return
    if isinstance(expr, CallNode):
        for a in expr.args:
            yield from _iter_nodes(a)
        return
    if isinstance(expr, UnaryNode):
        yield from _iter_nodes(expr.child)
        return
    if isinstance(expr, BinaryNode):
        yield from _iter_nodes(expr.left)
        yield from _iter_nodes(expr.right)
        return
    if isinstance(expr, (ComparisonNode, EventNode)):
        yield from _iter_nodes(expr.left)
        yield from _iter_nodes(expr.right)
        return
    if isinstance(expr, LogicalNode):
        for c in expr.children:
            yield from _iter_nodes(c)
        return
    if isinstance(expr, NotNode):
        yield from _iter_nodes(expr.child)
        return


def _needs_holdings_snapshot(expr: ExprNode) -> bool:
    for n in _iter_nodes(expr):
        if isinstance(n, IdentNode) and n.name.upper() in _HOLDINGS_SNAPSHOT_METRICS:
            return True
    return False


def _iter_alert_symbols(
    db: Session,
    settings: Settings,
    *,
    alert: AlertDefinition,
    user: User,
) -> Iterable[Tuple[str, str]]:
    kind = (alert.target_kind or "").upper()
    ref = (alert.target_ref or "").strip()
    exchange = (alert.exchange or "NSE").upper()

    if kind == "SYMBOL":
        if not ref:
            return
        yield ref.upper(), exchange
        return

    if kind == "GROUP":
        try:
            group_id = int(ref)
        except ValueError:
            return
        group = db.get(Group, group_id)
        if group is None:
            return
        if group.owner_id is not None and group.owner_id != user.id:
            return
        members = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == group_id)
            .order_by(GroupMember.created_at)
            .all()
        )
        for m in members:
            exch = (m.exchange or "NSE").upper()
            yield m.symbol.upper(), exch
        return

    if kind == "HOLDINGS":
        # Resolve live holdings for the alert's user.
        try:
            from app.api.positions import list_holdings

            holdings = list_holdings(db=db, settings=settings, user=user)
        except Exception:
            return
        for h in holdings:
            exch = (getattr(h, "exchange", None) or "NSE").upper()
            yield h.symbol.upper(), exch


def _get_last_event_for_symbol(
    db: Session,
    *,
    alert_id: int,
    user_id: int,
    symbol: str,
) -> Optional[AlertEvent]:
    return (
        db.query(AlertEvent)
        .filter(
            AlertEvent.alert_definition_id == alert_id,
            AlertEvent.user_id == user_id,
            AlertEvent.symbol == symbol,
        )
        .order_by(AlertEvent.triggered_at.desc())
        .first()
    )


def _should_emit_event(
    db: Session,
    *,
    alert: AlertDefinition,
    symbol: str,
    now: datetime,
    bar_time: Optional[datetime],
) -> bool:
    last = _get_last_event_for_symbol(
        db, alert_id=alert.id, user_id=alert.user_id, symbol=symbol
    )
    if alert.throttle_seconds and last is not None:
        if (
            last.triggered_at
            and (now - last.triggered_at).total_seconds() < alert.throttle_seconds
        ):
            return False

    mode = (alert.trigger_mode or "ONCE_PER_BAR").upper()
    if mode == "EVERY_TIME":
        return True
    if last is None:
        return True
    if mode == "ONCE":
        return False
    if mode == "ONCE_PER_BAR":
        if bar_time is None:
            return False
        return last.bar_time != bar_time
    return True


def evaluate_alerts_v3_once() -> None:
    settings = get_settings()
    now = _now_ist_naive()

    with SessionLocal() as db:
        alerts: List[AlertDefinition] = (
            db.query(AlertDefinition)
            .filter(
                AlertDefinition.enabled.is_(True),
                or_(
                    AlertDefinition.expires_at.is_(None),
                    AlertDefinition.expires_at >= now,
                ),
            )
            .order_by(AlertDefinition.updated_at.desc())
            .all()
        )
        if not alerts:
            return

        # Cache custom indicators per user.
        custom_by_user: Dict[int, CustomIndicatorMap] = {}
        users_by_id: Dict[int, User] = {}
        holdings_by_user: Dict[int, Dict[str, HoldingRead]] = {}

        for alert in alerts:
            try:
                if alert.only_market_hours and not is_market_open_now():
                    continue

                cadence = (alert.evaluation_cadence or "1m").strip().lower()
                try:
                    cadence_td = timeframe_to_timedelta(cadence)
                except IndicatorAlertError:
                    cadence_td = timedelta(minutes=1)

                if alert.last_evaluated_at is not None:
                    # Compare in IST-naive space.
                    last_eval = alert.last_evaluated_at
                    if last_eval.tzinfo is not None:
                        last_eval = last_eval.astimezone(UTC).replace(tzinfo=None)
                    if (now - last_eval) < cadence_td:
                        continue

                user = users_by_id.get(alert.user_id)
                if user is None:
                    user = db.get(User, alert.user_id)
                    if user is None:
                        continue
                    users_by_id[user.id] = user

                custom = custom_by_user.get(user.id)
                if custom is None:
                    custom = compile_custom_indicators_for_user(db, user_id=user.id)
                    custom_by_user[user.id] = custom

                # Compile condition AST if missing.
                if alert.condition_ast_json:
                    try:
                        cond_ast = loads_ast(alert.condition_ast_json)
                    except IndicatorAlertError:
                        cond_ast = compile_alert_definition(
                            db, alert=alert, user_id=user.id, custom_indicators=custom
                        )
                else:
                    cond_ast = compile_alert_definition(
                        db, alert=alert, user_id=user.id, custom_indicators=custom
                    )

                holdings_map = None
                if (
                    alert.target_kind or ""
                ).upper() == "HOLDINGS" or _needs_holdings_snapshot(cond_ast):
                    holdings_map = holdings_by_user.get(user.id)
                    if holdings_map is None:
                        try:
                            from app.api.positions import list_holdings

                            holdings = list_holdings(
                                db=db, settings=settings, user=user
                            )
                            holdings_map = {h.symbol.upper(): h for h in holdings}
                        except Exception:
                            holdings_map = {}
                        holdings_by_user[user.id] = holdings_map

                any_triggered = False
                for symbol, exchange in _iter_alert_symbols(
                    db, settings, alert=alert, user=user
                ):
                    try:
                        holding = (
                            holdings_map.get(symbol.upper())
                            if holdings_map is not None
                            else None
                        )
                        ok, snapshot, bar_time = eval_condition(
                            cond_ast,
                            db=db,
                            settings=settings,
                            symbol=symbol,
                            exchange=exchange,
                            holding=holding,
                            custom_indicators=custom,
                        )
                    except IndicatorAlertError:
                        continue

                    if not ok:
                        continue
                    if not _should_emit_event(
                        db, alert=alert, symbol=symbol, now=now, bar_time=bar_time
                    ):
                        continue

                    event = AlertEvent(
                        alert_definition_id=alert.id,
                        user_id=user.id,
                        symbol=symbol,
                        exchange=exchange,
                        evaluation_cadence=alert.evaluation_cadence,
                        reason=f"Matched: {alert.condition_dsl}",
                        snapshot_json=json.dumps(snapshot, default=str),
                        triggered_at=now,
                        bar_time=bar_time,
                    )
                    db.add(event)
                    any_triggered = True

                alert.last_evaluated_at = now
                if any_triggered:
                    alert.last_triggered_at = now
                db.add(alert)
            except Exception:
                # Skip malformed rules without failing the whole batch.
                continue

        db.commit()


def _alerts_v3_loop() -> None:  # pragma: no cover - background loop
    interval = timedelta(seconds=15)
    next_run = _now_ist_naive() + timedelta(seconds=5)

    while not _scheduler_stop_event.is_set():
        now = _now_ist_naive()
        sleep_for = (next_run - now).total_seconds()
        if sleep_for > 0:
            _scheduler_stop_event.wait(timeout=sleep_for)
            if _scheduler_stop_event.is_set():
                return

        try:
            evaluate_alerts_v3_once()
        except Exception:
            pass

        next_run = _now_ist_naive() + interval


def schedule_alerts_v3() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    thread = Thread(
        target=_alerts_v3_loop,
        name="alerts-v3",
        daemon=True,
    )
    thread.start()


__all__ = ["AlertsV3Error", "evaluate_alerts_v3_once", "schedule_alerts_v3"]
