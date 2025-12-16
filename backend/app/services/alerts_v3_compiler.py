from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Set, Tuple

from sqlalchemy.orm import Session

from app.models import AlertDefinition, CustomIndicator
from app.services.alerts_v3_dsl import parse_v3_expression
from app.services.alerts_v3_expression import (
    _ALLOWED_METRICS,
    BinaryNode,
    CallNode,
    ComparisonNode,
    EventNode,
    ExprNode,
    IdentNode,
    LogicalNode,
    NotNode,
    NumberNode,
    UnaryNode,
    dumps_ast,
    loads_ast,
    timeframe_to_timedelta,
)
from app.services.indicator_alerts import IndicatorAlertError


@dataclass(frozen=True)
class CompiledCustomIndicator:
    name: str
    param_names: List[str]
    body: ExprNode


CustomIndicatorMap = Dict[str, Tuple[List[str], ExprNode]]


_CUSTOM_INDICATOR_ALLOWED_BUILTINS: Set[str] = {
    # MVP surface (Phase A) from docs/alerts_refactor_v3.md
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    "VOLUME",
    "PRICE",  # alias for CLOSE
    "SMA",
    "EMA",
    "RSI",
    "ATR",
    "STDDEV",
    "RET",
    "MAX",
    "MIN",
    "AVG",
    "SUM",
    # Math helpers
    "ABS",
    "SQRT",
    "LOG",
    "EXP",
    "POW",
}


def _load_json_list(raw: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IndicatorAlertError("Invalid JSON payload") from exc
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise IndicatorAlertError("Expected a list")
    out: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            out.append(item)
    return out


def _is_valid_ident(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""))


def _walk(node: ExprNode) -> Iterable[ExprNode]:
    yield node
    if isinstance(node, (NumberNode, IdentNode)):
        return
    if isinstance(node, CallNode):
        for a in node.args:
            yield from _walk(a)
        return
    if isinstance(node, UnaryNode):
        yield from _walk(node.child)
        return
    if isinstance(node, BinaryNode):
        yield from _walk(node.left)
        yield from _walk(node.right)
        return
    if isinstance(node, (ComparisonNode, EventNode)):
        yield from _walk(node.left)
        yield from _walk(node.right)
        return
    if isinstance(node, LogicalNode):
        for c in node.children:
            yield from _walk(c)
        return
    if isinstance(node, NotNode):
        yield from _walk(node.child)
        return


def _ensure_numeric_only(expr: ExprNode, *, context: str) -> None:
    for n in _walk(expr):
        if isinstance(n, (ComparisonNode, EventNode, LogicalNode, NotNode)):
            raise IndicatorAlertError(f"{context} must be a numeric expression")


def _validate_custom_indicator_ast(expr: ExprNode, *, name: str) -> None:
    _ensure_numeric_only(expr, context=f"Custom indicator '{name}'")
    for n in _walk(expr):
        if isinstance(n, CallNode):
            fn = n.name.upper()
            if fn not in _CUSTOM_INDICATOR_ALLOWED_BUILTINS:
                raise IndicatorAlertError(
                    f"Custom indicator '{name}' uses unsupported function '{n.name}'"
                )


def compile_custom_indicators_for_user(
    db: Session,
    *,
    user_id: int,
) -> CustomIndicatorMap:
    indicators: list[CustomIndicator] = (
        db.query(CustomIndicator)
        .filter(CustomIndicator.user_id == user_id, CustomIndicator.enabled.is_(True))
        .order_by(CustomIndicator.updated_at.desc())
        .all()
    )
    compiled: CustomIndicatorMap = {}
    for ind in indicators:
        name = (ind.name or "").strip()
        if not name or not _is_valid_ident(name):
            continue

        params: list[str] = []
        try:
            raw_params = json.loads(ind.params_json or "[]")
            if isinstance(raw_params, list):
                for p in raw_params:
                    if isinstance(p, str) and _is_valid_ident(p):
                        params.append(p.upper())
                    elif isinstance(p, dict):
                        pname = p.get("name")
                        if isinstance(pname, str) and _is_valid_ident(pname):
                            params.append(pname.upper())
        except json.JSONDecodeError:
            params = []

        if ind.body_ast_json:
            try:
                body = loads_ast(ind.body_ast_json)
            except IndicatorAlertError:
                body = parse_v3_expression(ind.body_dsl)
        else:
            body = parse_v3_expression(ind.body_dsl)

        _validate_custom_indicator_ast(body, name=name)

        # Persist compiled AST if missing or invalid.
        if not ind.body_ast_json:
            ind.body_ast_json = dumps_ast(body)
            db.add(ind)

        compiled[name.upper()] = (params, body)

    return compiled


def _substitute_idents(expr: ExprNode, mapping: Dict[str, ExprNode]) -> ExprNode:
    if isinstance(expr, IdentNode):
        repl = mapping.get(expr.name.upper())
        return repl if repl is not None else expr
    if isinstance(expr, NumberNode):
        return expr
    if isinstance(expr, CallNode):
        return CallNode(expr.name, [_substitute_idents(a, mapping) for a in expr.args])
    if isinstance(expr, UnaryNode):
        return UnaryNode(expr.op, _substitute_idents(expr.child, mapping))
    if isinstance(expr, BinaryNode):
        return BinaryNode(
            expr.op,
            _substitute_idents(expr.left, mapping),
            _substitute_idents(expr.right, mapping),
        )
    if isinstance(expr, ComparisonNode):
        return ComparisonNode(
            expr.op,
            _substitute_idents(expr.left, mapping),
            _substitute_idents(expr.right, mapping),
        )
    if isinstance(expr, EventNode):
        return EventNode(
            expr.op,
            _substitute_idents(expr.left, mapping),
            _substitute_idents(expr.right, mapping),
        )
    if isinstance(expr, LogicalNode):
        return LogicalNode(
            expr.op, [_substitute_idents(c, mapping) for c in expr.children]
        )
    if isinstance(expr, NotNode):
        return NotNode(_substitute_idents(expr.child, mapping))
    return expr


def _build_variable_ast(var: dict[str, Any]) -> tuple[str, ExprNode]:
    name = str(var.get("name") or "").strip()
    if not _is_valid_ident(name):
        raise IndicatorAlertError("Variable name must be a valid identifier")

    if isinstance(var.get("dsl"), str) and var.get("dsl").strip():
        expr = parse_v3_expression(var["dsl"])
        _ensure_numeric_only(expr, context=f"Variable '{name}'")
        return name.upper(), expr

    kind = str(var.get("kind") or "").strip().upper()
    params = var.get("params") if isinstance(var.get("params"), dict) else {}

    if kind in {"METRIC"}:
        metric = str(params.get("metric") or params.get("name") or "").strip().upper()
        if metric not in _ALLOWED_METRICS:
            raise IndicatorAlertError(
                f"Unknown metric '{metric}' for variable '{name}'"
            )
        return name.upper(), IdentNode(metric)

    if kind in {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}:
        tf = str(params.get("timeframe") or "1d")
        return name.upper(), CallNode(kind, [IdentNode(tf)])

    if kind in {"PRICE"}:
        tf = str(params.get("timeframe") or "1d")
        return name.upper(), CallNode("CLOSE", [IdentNode(tf)])

    if kind in {"SMA", "EMA", "RSI", "STDDEV", "MAX", "MIN", "AVG", "SUM"}:
        source = str(params.get("source") or "close")
        length = int(params.get("length") or params.get("window") or 14)
        tf = str(params.get("timeframe") or "1d")
        return name.upper(), CallNode(
            kind, [IdentNode(source), NumberNode(length), IdentNode(tf)]
        )

    if kind in {"RET"}:
        source = str(params.get("source") or "close")
        tf = str(params.get("timeframe") or "1d")
        return name.upper(), CallNode("RET", [IdentNode(source), IdentNode(tf)])

    if kind in {"ATR"}:
        length = int(params.get("length") or params.get("window") or 14)
        tf = str(params.get("timeframe") or "1d")
        return name.upper(), CallNode("ATR", [NumberNode(length), IdentNode(tf)])

    if kind in {"CUSTOM"}:
        fn = str(params.get("function") or params.get("name") or "").strip()
        if not _is_valid_ident(fn):
            raise IndicatorAlertError(
                f"Invalid custom indicator name for variable '{name}'"
            )
        raw_args = params.get("args")
        args: list[ExprNode] = []
        if isinstance(raw_args, list):
            for a in raw_args:
                if isinstance(a, (int, float)):
                    args.append(NumberNode(float(a)))
                elif isinstance(a, str):
                    args.append(parse_v3_expression(a))
                elif isinstance(a, dict) and isinstance(a.get("dsl"), str):
                    args.append(parse_v3_expression(a["dsl"]))
        return name.upper(), CallNode(fn, args)

    raise IndicatorAlertError(f"Variable '{name}' is missing a definition")


def _collect_timeframes(expr: ExprNode) -> Set[str]:
    tfs: Set[str] = set()
    for n in _walk(expr):
        if isinstance(n, CallNode):
            fn = n.name.upper()
            if fn in {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"} and len(n.args) == 1:
                if isinstance(n.args[0], IdentNode):
                    tfs.add(n.args[0].name.strip().strip('"').strip("'").lower())
            if fn == "PRICE":
                if len(n.args) == 1 and isinstance(n.args[0], IdentNode):
                    tfs.add(n.args[0].name.strip().strip('"').strip("'").lower())
                if len(n.args) == 2 and isinstance(n.args[1], IdentNode):
                    tfs.add(n.args[1].name.strip().strip('"').strip("'").lower())
            if fn in {"SMA", "EMA", "RSI", "STDDEV", "MAX", "MIN", "AVG", "SUM"}:
                if len(n.args) == 3 and isinstance(n.args[2], IdentNode):
                    tfs.add(n.args[2].name.strip().strip('"').strip("'").lower())
                if len(n.args) == 2:
                    tfs.add("1d")
            if fn == "RET" and len(n.args) == 2 and isinstance(n.args[1], IdentNode):
                tfs.add(n.args[1].name.strip().strip('"').strip("'").lower())
            if fn == "ATR" and len(n.args) in {2, 3}:
                tf_node = n.args[-1]
                if isinstance(tf_node, IdentNode):
                    tfs.add(tf_node.name.strip().strip('"').strip("'").lower())
    return tfs


def _pick_default_cadence(timeframes: Set[str]) -> str:
    if not timeframes:
        return "1m"
    # Choose the smallest timeframe duration.
    best = None
    for tf in timeframes:
        try:
            dt = timeframe_to_timedelta(tf)
        except IndicatorAlertError:
            continue
        if best is None or dt < best[0]:
            best = (dt, tf)
    return best[1] if best else "1m"


def compile_alert_definition(
    db: Session,
    *,
    alert: AlertDefinition,
    user_id: int,
    custom_indicators: CustomIndicatorMap | None = None,
) -> ExprNode:
    """Compile the alert's condition DSL into an AST with variables inlined."""

    custom_indicators = custom_indicators or compile_custom_indicators_for_user(
        db, user_id=user_id
    )

    raw_vars = _load_json_list(alert.variables_json or "[]")
    var_map: Dict[str, ExprNode] = {}
    referenced_timeframes: Set[str] = set()

    for item in raw_vars:
        vname, expr = _build_variable_ast(item)
        # Allow variables to reference previous variables only.
        expr = _substitute_idents(expr, var_map)
        _ensure_numeric_only(expr, context=f"Variable '{vname}'")
        var_map[vname] = expr
        referenced_timeframes |= _collect_timeframes(expr)

    condition_ast = parse_v3_expression(alert.condition_dsl)
    condition_ast = _substitute_idents(condition_ast, var_map)
    referenced_timeframes |= _collect_timeframes(condition_ast)

    # Validate MOVING_* RHS numeric-only
    for n in _walk(condition_ast):
        if isinstance(n, EventNode) and n.op.upper() in {"MOVING_UP", "MOVING_DOWN"}:
            if not isinstance(n.right, NumberNode):
                raise IndicatorAlertError(
                    "MOVING_UP/DOWN RHS must be a numeric constant"
                )

    # Validate function calls exist (built-ins + custom indicators)
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
            # Built-ins are validated at evaluation time as well; keep a minimal
            # allowlist here.
            if fn not in _CUSTOM_INDICATOR_ALLOWED_BUILTINS:
                raise IndicatorAlertError(f"Unknown function '{n.name}'")

    # Auto-fill cadence when unset/blank.
    if not (alert.evaluation_cadence or "").strip():
        alert.evaluation_cadence = _pick_default_cadence(referenced_timeframes)
        db.add(alert)

    alert.condition_ast_json = dumps_ast(condition_ast)
    db.add(alert)
    return condition_ast


def compile_alert_expression(
    db: Session,
    *,
    user_id: int,
    variables: list[dict[str, Any]],
    condition_dsl: str,
    evaluation_cadence: str | None = None,
    custom_indicators: CustomIndicatorMap | None = None,
) -> tuple[ExprNode, str]:
    """Compile (variables + condition DSL) without persisting an AlertDefinition.

    Used by preview/test endpoints and UI tooling.
    """

    custom_indicators = custom_indicators or compile_custom_indicators_for_user(
        db, user_id=user_id
    )

    var_map: Dict[str, ExprNode] = {}
    referenced_timeframes: Set[str] = set()

    for item in variables:
        vname, expr = _build_variable_ast(item)
        expr = _substitute_idents(expr, var_map)
        _ensure_numeric_only(expr, context=f"Variable '{vname}'")
        var_map[vname] = expr
        referenced_timeframes |= _collect_timeframes(expr)

    condition_ast = parse_v3_expression(condition_dsl)
    condition_ast = _substitute_idents(condition_ast, var_map)
    referenced_timeframes |= _collect_timeframes(condition_ast)

    for n in _walk(condition_ast):
        if isinstance(n, EventNode) and n.op.upper() in {"MOVING_UP", "MOVING_DOWN"}:
            if not isinstance(n.right, NumberNode):
                raise IndicatorAlertError(
                    "MOVING_UP/DOWN RHS must be a numeric constant"
                )

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
            if fn not in _CUSTOM_INDICATOR_ALLOWED_BUILTINS:
                raise IndicatorAlertError(f"Unknown function '{n.name}'")

    cadence = (evaluation_cadence or "").strip()
    if not cadence:
        cadence = _pick_default_cadence(referenced_timeframes)

    return condition_ast, cadence


__all__ = [
    "compile_custom_indicators_for_user",
    "compile_alert_definition",
    "compile_alert_expression",
    "CustomIndicatorMap",
]
