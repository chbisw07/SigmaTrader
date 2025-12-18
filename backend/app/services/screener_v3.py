from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Optional, Set

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models import Group, GroupMember, ScreenerRun, User
from app.schemas.alerts_v3 import AlertVariableDef
from app.schemas.screener_v3 import ScreenerRow
from app.services.alerts_v3_compiler import (
    CustomIndicatorMap,
    compile_alert_expression_parts,
    compile_custom_indicators_for_user,
)
from app.services.alerts_v3_dsl import parse_v3_expression
from app.services.alerts_v3_expression import (
    _eval_numeric,  # intentionally reused here for efficient value extraction
)
from app.services.alerts_v3_expression import (
    CandleCache,
    ComparisonNode,
    EventNode,
    ExprNode,
    IndicatorAlertError,
    LogicalNode,
    NotNode,
    NumberNode,
)


class ScreenerV3Error(RuntimeError):
    """Raised when a screener run cannot be completed."""


def _model_dump(obj) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[attr-defined]
    return obj.dict()  # type: ignore[attr-defined]


def _iter_target_symbols(
    db: Session,
    settings: Settings,
    *,
    user: User,
    include_holdings: bool,
    group_ids: list[int],
) -> list[tuple[str, str]]:
    seen: Set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []

    if include_holdings:
        try:
            from app.api.positions import list_holdings

            holdings = list_holdings(db=db, settings=settings, user=user)
        except Exception:
            holdings = []
        for h in holdings:
            symbol = (h.symbol or "").strip().upper()
            if not symbol:
                continue
            exch = (getattr(h, "exchange", None) or "NSE").upper()
            key = (symbol, exch)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)

    if group_ids:
        allowed_groups: list[int] = []
        rows = (
            db.query(Group)
            .filter(Group.id.in_(group_ids))  # type: ignore[arg-type]
            .all()
        )
        for g in rows:
            if g.owner_id is None or g.owner_id == user.id:
                allowed_groups.append(g.id)
        if allowed_groups:
            members = (
                db.query(GroupMember)
                .filter(GroupMember.group_id.in_(allowed_groups))  # type: ignore[arg-type]
                .order_by(GroupMember.created_at)
                .all()
            )
            for m in members:
                symbol = (m.symbol or "").strip().upper()
                if not symbol:
                    continue
                exch = (m.exchange or "NSE").upper()
                key = (symbol, exch)
                if key in seen:
                    continue
                seen.add(key)
                out.append(key)

    return out


def resolve_screener_targets(
    db: Session,
    settings: Settings,
    *,
    user: User,
    include_holdings: bool,
    group_ids: list[int],
) -> list[tuple[str, str]]:
    return _iter_target_symbols(
        db,
        settings,
        user=user,
        include_holdings=include_holdings,
        group_ids=group_ids,
    )


def _build_default_column_asts() -> dict[str, ExprNode]:
    # Keep these conservative (daily indicators) to avoid heavy 1m fetches.
    return {
        "close_1d": parse_v3_expression("PRICE(1d)"),
        "rsi_14_1d": parse_v3_expression("RSI(close, 14, 1d)"),
        "sma_20_1d": parse_v3_expression("SMA(close, 20, 1d)"),
        "sma_50_1d": parse_v3_expression("SMA(close, 50, 1d)"),
    }


def _eval_condition_with_cache(
    cond_ast: ExprNode,
    *,
    db: Session,
    settings: Settings,
    cache: CandleCache,
    holding,
    custom_indicators: CustomIndicatorMap,
    allow_fetch: bool,
) -> tuple[bool, bool, Optional[datetime]]:
    missing = False

    def _bool(n: ExprNode) -> bool:
        nonlocal missing
        if isinstance(n, LogicalNode):
            op = n.op.upper()
            if op == "AND":
                return all(_bool(c) for c in n.children)
            if op == "OR":
                return any(_bool(c) for c in n.children)
            raise IndicatorAlertError(f"Unknown logical op '{n.op}'")
        if isinstance(n, NotNode):
            return not _bool(n.child)
        if isinstance(n, ComparisonNode):
            left = _eval_numeric(
                n.left,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            right = _eval_numeric(
                n.right,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if left.now is None or right.now is None:
                missing = True
                return False
            op = n.op
            if op == "GT":
                return left.now > right.now
            if op == "GTE":
                return left.now >= right.now
            if op == "LT":
                return left.now < right.now
            if op == "LTE":
                return left.now <= right.now
            if op == "EQ":
                return left.now == right.now
            if op == "NEQ":
                return left.now != right.now
            raise IndicatorAlertError(f"Unknown comparison op '{op}'")
        if isinstance(n, EventNode):
            op = n.op.upper()
            left = _eval_numeric(
                n.left,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            right = _eval_numeric(
                n.right,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if op in {"CROSSES_ABOVE", "CROSSES_BELOW"}:
                if left.prev is None or left.now is None:
                    missing = True
                    return False
                if isinstance(n.right, NumberNode):
                    level = float(n.right.value)
                    if op == "CROSSES_ABOVE":
                        return left.prev <= level < left.now
                    return left.prev >= level > left.now
                if right.prev is None or right.now is None:
                    missing = True
                    return False
                if op == "CROSSES_ABOVE":
                    return left.prev <= right.prev and left.now > right.now
                return left.prev >= right.prev and left.now < right.now

            if op in {"MOVING_UP", "MOVING_DOWN"}:
                if left.prev is None or left.now is None:
                    missing = True
                    return False
                if right.now is None:
                    missing = True
                    return False
                if left.prev == 0:
                    missing = True
                    return False
                change_pct = (left.now - left.prev) / abs(left.prev) * 100.0
                threshold = float(right.now)
                if op == "MOVING_UP":
                    return change_pct >= threshold
                return (-change_pct) >= threshold

            raise IndicatorAlertError(f"Unknown event op '{n.op}'")

        v = _eval_numeric(
            n,
            db=db,
            settings=settings,
            cache=cache,
            holding=holding,
            params={},
            custom_indicators=custom_indicators,
            allow_fetch=allow_fetch,
        )
        if v.now is None:
            missing = True
        return bool(v.now)

    matched = _bool(cond_ast)
    _, bar_time = cache.series("1d", "close")
    return matched, missing, bar_time


def evaluate_screener_v3(
    db: Session,
    settings: Settings,
    *,
    user: User,
    include_holdings: bool,
    group_ids: list[int],
    variables: list[AlertVariableDef],
    condition_dsl: str,
    evaluation_cadence: str | None,
    allow_fetch: bool,
) -> tuple[list[ScreenerRow], str, dict[str, int]]:
    custom = compile_custom_indicators_for_user(db, user_id=user.id)
    vars_dicts = [_model_dump(v) for v in variables]
    cond_ast, cadence, var_map = compile_alert_expression_parts(
        db,
        user_id=user.id,
        variables=vars_dicts,
        condition_dsl=condition_dsl,
        evaluation_cadence=evaluation_cadence,
        custom_indicators=custom,
    )

    targets = _iter_target_symbols(
        db,
        settings,
        user=user,
        include_holdings=include_holdings,
        group_ids=group_ids,
    )

    holdings_map: dict[str, object] = {}
    if include_holdings:
        try:
            from app.api.positions import list_holdings

            holdings = list_holdings(db=db, settings=settings, user=user)
            holdings_map = {h.symbol.upper(): h for h in holdings if h.symbol}
        except Exception:
            holdings_map = {}

    col_asts = _build_default_column_asts()

    rows: list[ScreenerRow] = []
    evaluated = 0
    matched_count = 0
    missing_count = 0
    for symbol, exchange in targets:
        evaluated += 1
        holding = holdings_map.get(symbol.upper())
        try:
            cache = CandleCache(
                db=db,
                settings=settings,
                symbol=symbol,
                exchange=exchange,
                allow_fetch=allow_fetch,
            )
            matched, missing_data, _bar_time = _eval_condition_with_cache(
                cond_ast,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                custom_indicators=custom,
                allow_fetch=allow_fetch,
            )
            last_price = None
            if holding is not None and getattr(holding, "last_price", None) is not None:
                try:
                    last_price = float(holding.last_price)
                except Exception:
                    last_price = None

            close_1d = _eval_numeric(
                col_asts["close_1d"],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom,
                allow_fetch=allow_fetch,
            ).now

            if last_price is None and close_1d is not None:
                last_price = float(close_1d)

            rsi = _eval_numeric(
                col_asts["rsi_14_1d"],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom,
                allow_fetch=allow_fetch,
            ).now
            sma20 = _eval_numeric(
                col_asts["sma_20_1d"],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom,
                allow_fetch=allow_fetch,
            ).now
            sma50 = _eval_numeric(
                col_asts["sma_50_1d"],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params={},
                custom_indicators=custom,
                allow_fetch=allow_fetch,
            ).now

            var_values: dict[str, Optional[float]] = {}
            for vname, vexpr in var_map.items():
                val = _eval_numeric(
                    vexpr,
                    db=db,
                    settings=settings,
                    cache=cache,
                    holding=holding,
                    params={},
                    custom_indicators=custom,
                    allow_fetch=allow_fetch,
                ).now
                var_values[vname] = float(val) if val is not None else None

            if matched:
                matched_count += 1
            if missing_data:
                missing_count += 1

            rows.append(
                ScreenerRow(
                    symbol=symbol,
                    exchange=exchange,
                    matched=matched,
                    missing_data=missing_data,
                    last_price=float(last_price) if last_price is not None else None,
                    rsi_14_1d=float(rsi) if rsi is not None else None,
                    sma_20_1d=float(sma20) if sma20 is not None else None,
                    sma_50_1d=float(sma50) if sma50 is not None else None,
                    variables=var_values,
                )
            )
        except IndicatorAlertError as exc:
            missing_count += 1
            rows.append(
                ScreenerRow(
                    symbol=symbol,
                    exchange=exchange,
                    matched=False,
                    missing_data=True,
                    error=str(exc),
                )
            )
        except Exception as exc:
            missing_count += 1
            rows.append(
                ScreenerRow(
                    symbol=symbol,
                    exchange=exchange,
                    matched=False,
                    missing_data=True,
                    error=str(exc),
                )
            )

    stats = {
        "total_symbols": len(targets),
        "evaluated_symbols": evaluated,
        "matched_symbols": matched_count,
        "missing_symbols": missing_count,
    }
    return rows, cadence, stats


def create_screener_run(
    db: Session,
    *,
    user: User,
    include_holdings: bool,
    group_ids: list[int],
    variables_json: str,
    condition_dsl: str,
    evaluation_cadence: str,
    total_symbols: int,
) -> ScreenerRun:
    target = {"include_holdings": include_holdings, "group_ids": group_ids}
    run = ScreenerRun(
        user_id=user.id,
        status="RUNNING",
        target_json=json.dumps(target, default=str),
        variables_json=variables_json,
        condition_dsl=condition_dsl,
        evaluation_cadence=evaluation_cadence,
        total_symbols=total_symbols,
        evaluated_symbols=0,
        matched_symbols=0,
        missing_symbols=0,
        results_json="[]",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _run_screener_in_thread(run_id: int) -> None:  # pragma: no cover
    settings = get_settings()
    with SessionLocal() as db:
        run = db.get(ScreenerRun, run_id)
        if run is None:
            return
        user = db.get(User, run.user_id)
        if user is None:
            run.status = "ERROR"
            run.error = "User not found."
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.commit()
            return
        try:
            target = json.loads(run.target_json or "{}")
            include_holdings = bool(target.get("include_holdings"))
            group_ids = [int(x) for x in (target.get("group_ids") or [])]
            vars_raw = json.loads(run.variables_json or "[]")
            variables = [AlertVariableDef(**v) for v in vars_raw if isinstance(v, dict)]

            rows, cadence, stats = evaluate_screener_v3(
                db,
                settings,
                user=user,
                include_holdings=include_holdings,
                group_ids=group_ids,
                variables=variables,
                condition_dsl=run.condition_dsl or "",
                evaluation_cadence=run.evaluation_cadence,
                allow_fetch=False,
            )
            run.evaluation_cadence = cadence
            run.status = "DONE"
            run.evaluated_symbols = stats["evaluated_symbols"]
            run.matched_symbols = stats["matched_symbols"]
            run.missing_symbols = stats["missing_symbols"]
            run.results_json = json.dumps([_model_dump(r) for r in rows], default=str)
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.commit()
        except Exception as exc:
            run.status = "ERROR"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.commit()


def start_screener_run_async(run_id: int) -> None:
    t = threading.Thread(
        target=_run_screener_in_thread,
        args=(run_id,),
        daemon=True,
        name=f"screener-v3-run-{run_id}",
    )
    t.start()
