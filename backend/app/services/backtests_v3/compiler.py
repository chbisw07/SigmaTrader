from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set, Tuple

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.alerts_v3_compiler import (
    CustomIndicatorMap,
    _dsl_allowed_builtins,
    _ensure_numeric_only,
    _is_valid_ident,
    _split_inline_variables,
    _substitute_idents,
    _walk,
    compile_custom_indicators_for_user,
)
from app.services.alerts_v3_dsl import parse_v3_expression
from app.services.alerts_v3_expression import (
    CallNode,
    EventNode,
    ExprNode,
    IdentNode,
    NumberNode,
)
from app.services.indicator_alerts import IndicatorAlertError


@dataclass(frozen=True)
class CompiledV3Condition:
    ast: ExprNode
    referenced_timeframes: Set[str]


def _strip_tf(raw: str) -> str:
    return str(raw or "").strip().strip('"').strip("'").lower()


def _collect_timeframes(expr: ExprNode, *, default_tf: str) -> Set[str]:
    """Collect timeframes referenced by v3 expressions.

    Note: This is used for safety + data loading, not for cadence selection.
    """

    tfs: Set[str] = set()
    for n in _walk(expr):
        if isinstance(n, CallNode):
            fn = n.name.upper()
            if fn in {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"} and len(n.args) == 1:
                if isinstance(n.args[0], IdentNode):
                    tfs.add(_strip_tf(n.args[0].name))
            elif fn == "PRICE":
                if len(n.args) == 1 and isinstance(n.args[0], IdentNode):
                    tfs.add(_strip_tf(n.args[0].name))
                elif len(n.args) == 2 and isinstance(n.args[1], IdentNode):
                    tfs.add(_strip_tf(n.args[1].name))
            elif fn in {
                "SMA",
                "EMA",
                "RSI",
                "STDDEV",
                "MAX",
                "MIN",
                "AVG",
                "SUM",
            }:
                if len(n.args) == 3 and isinstance(n.args[2], IdentNode):
                    tfs.add(_strip_tf(n.args[2].name))
                else:
                    tfs.add(default_tf)
            elif fn in {"ATR", "ADX"}:
                if len(n.args) == 2 and isinstance(n.args[1], IdentNode):
                    tfs.add(_strip_tf(n.args[1].name))
                else:
                    tfs.add(default_tf)
            elif fn == "RET":
                if len(n.args) == 2 and isinstance(n.args[1], IdentNode):
                    tfs.add(_strip_tf(n.args[1].name))
            elif fn in {"OBV", "VWAP"}:
                if len(n.args) == 3 and isinstance(n.args[2], IdentNode):
                    tfs.add(_strip_tf(n.args[2].name))
                else:
                    tfs.add(default_tf)
            elif fn in {"MACD", "MACD_SIGNAL", "MACD_HIST"}:
                if len(n.args) == 5 and isinstance(n.args[4], IdentNode):
                    tfs.add(_strip_tf(n.args[4].name))
                else:
                    tfs.add(default_tf)
            elif fn in {"SUPERTREND_LINE", "SUPERTREND_DIR"}:
                # ([source], len, mult, [tf])
                if len(n.args) in {3, 4} and isinstance(n.args[-1], IdentNode):
                    maybe = _strip_tf(n.args[-1].name)
                    if maybe:
                        tfs.add(maybe)
                    else:
                        tfs.add(default_tf)
                else:
                    tfs.add(default_tf)
    return {tf for tf in tfs if tf}


def compile_v3_condition(
    db: Session,
    settings: Settings,
    *,
    user_id: int | None,
    dsl_text: str,
    base_timeframe: str,
    dsl_profile: str | None = None,
) -> Tuple[ExprNode, Set[str], CustomIndicatorMap]:
    """Compile a v3 DSL condition for backtesting.

    - Supports inline variable assignments (NAME = expr).
    - Supports custom indicators (user scoped) by validating call arity.
    - Enforces numeric-only constraints where required (e.g., MOVING_UP RHS).
    """

    allowed_builtins = _dsl_allowed_builtins(dsl_profile)
    custom_indicators: CustomIndicatorMap = {}
    if user_id is not None:
        custom_indicators = compile_custom_indicators_for_user(
            db, user_id=user_id, dsl_profile=dsl_profile
        )

    inline_defs, expr_text = _split_inline_variables(dsl_text or "")
    var_map: Dict[str, ExprNode] = {}

    for name, rhs in inline_defs:
        vname = name.upper()
        if not _is_valid_ident(vname):
            raise IndicatorAlertError(f"Invalid inline variable name '{name}'")
        expr = parse_v3_expression(rhs)
        expr = _substitute_idents(expr, var_map)
        _ensure_numeric_only(expr, context=f"Variable '{vname}'")
        var_map[vname] = expr

    if not expr_text.strip():
        raise IndicatorAlertError("Condition is empty.")

    condition_ast = parse_v3_expression(expr_text)
    condition_ast = _substitute_idents(condition_ast, var_map)

    for n in _walk(condition_ast):
        if isinstance(n, EventNode) and n.op.upper() in {"MOVING_UP", "MOVING_DOWN"}:
            if not isinstance(n.right, NumberNode):
                raise IndicatorAlertError("MOVING_UP/DOWN RHS must be a numeric constant")

    known_custom = set(custom_indicators.keys())
    for n in _walk(condition_ast):
        if isinstance(n, CallNode):
            fn = n.name.upper()
            if fn in known_custom:
                expected, _body = custom_indicators[fn]
                if len(n.args) != len(expected):
                    raise IndicatorAlertError(
                        f"{fn} expects {len(expected)} args but got {len(n.args)}"
                    )
                continue
            if fn not in allowed_builtins:
                raise IndicatorAlertError(f"Unknown function '{n.name}'")

    referenced_timeframes = _collect_timeframes(condition_ast, default_tf=base_timeframe)
    if not referenced_timeframes:
        referenced_timeframes = {base_timeframe}

    return condition_ast, referenced_timeframes, custom_indicators


__all__ = ["compile_v3_condition", "CompiledV3Condition"]
