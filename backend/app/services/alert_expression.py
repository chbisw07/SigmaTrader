from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from app.core.config import Settings
from app.db.session import Session
from app.models import Position
from app.schemas.indicator_rules import IndicatorType
from app.services.indicator_alerts import (
    IndicatorAlertError,
    IndicatorCondition,
    IndicatorSample,
    _compute_indicator_sample,
    _load_candles_for_rule,
)
from app.services.market_data import Timeframe

# -----------------------------------------------------------------------------
# AST types
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    kind: IndicatorType
    timeframe: Timeframe
    params: Dict[str, Any]


@dataclass(frozen=True)
class IndicatorOperand:
    node_type: str
    spec: IndicatorSpec

    def __init__(self, spec: IndicatorSpec) -> None:
        object.__setattr__(self, "node_type", "INDICATOR")
        object.__setattr__(self, "spec", spec)


@dataclass(frozen=True)
class NumberOperand:
    node_type: str
    value: float

    def __init__(self, value: float) -> None:
        object.__setattr__(self, "node_type", "NUMBER")
        object.__setattr__(self, "value", float(value))


@dataclass(frozen=True)
class FieldOperand:
    node_type: str
    name: str

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "node_type", "FIELD")
        object.__setattr__(self, "name", name)


Operand = Union[IndicatorOperand, NumberOperand, FieldOperand]


ComparisonOp = Union[
    str
]  # Runtime validated; expected: GT, GTE, LT, LTE, EQ, NEQ, CROSS_ABOVE, CROSS_BELOW
LogicalOp = Union[str]  # AND, OR


@dataclass
class ComparisonNode:
    node_type: str
    left: Operand
    operator: ComparisonOp
    right: Operand

    def __init__(self, left: Operand, operator: ComparisonOp, right: Operand) -> None:
        self.node_type = "COMPARISON"
        self.left = left
        self.operator = operator
        self.right = right


@dataclass
class LogicalNode:
    node_type: str
    op: LogicalOp
    children: List["ExpressionNode"]

    def __init__(self, op: LogicalOp, children: List["ExpressionNode"]) -> None:
        self.node_type = "LOGICAL"
        self.op = op
        self.children = children


@dataclass
class NotNode:
    node_type: str
    child: "ExpressionNode"

    def __init__(self, child: "ExpressionNode") -> None:
        self.node_type = "NOT"
        self.child = child


ExpressionNode = Union[ComparisonNode, LogicalNode, NotNode]


# -----------------------------------------------------------------------------
# Serialization helpers (for expression_json)
# -----------------------------------------------------------------------------


def _indicator_spec_to_dict(spec: IndicatorSpec) -> Dict[str, Any]:
    return {
        "kind": spec.kind,
        "timeframe": spec.timeframe,
        "params": dict(spec.params or {}),
    }


def _operand_to_dict(op: Operand) -> Dict[str, Any]:
    if isinstance(op, IndicatorOperand):
        return {
            "type": "INDICATOR",
            "spec": _indicator_spec_to_dict(op.spec),
        }
    if isinstance(op, NumberOperand):
        return {
            "type": "NUMBER",
            "value": op.value,
        }
    if isinstance(op, FieldOperand):
        return {
            "type": "FIELD",
            "name": op.name,
        }
    raise ValueError(f"Unsupported operand: {op!r}")


def expression_to_dict(expr: ExpressionNode) -> Dict[str, Any]:
    if isinstance(expr, ComparisonNode):
        return {
            "type": "COMPARISON",
            "operator": expr.operator,
            "left": _operand_to_dict(expr.left),
            "right": _operand_to_dict(expr.right),
        }
    if isinstance(expr, LogicalNode):
        return {
            "type": "LOGICAL",
            "op": expr.op,
            "children": [expression_to_dict(child) for child in expr.children],
        }
    if isinstance(expr, NotNode):
        return {
            "type": "NOT",
            "child": expression_to_dict(expr.child),
        }
    raise ValueError(f"Unsupported expression node: {expr!r}")


def _dict_to_indicator_spec(data: Dict[str, Any]) -> IndicatorSpec:
    kind = data.get("kind")
    timeframe = data.get("timeframe")
    if not isinstance(kind, str) or not isinstance(timeframe, str):
        raise IndicatorAlertError("Invalid indicator spec in expression_json")
    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    return IndicatorSpec(kind=kind, timeframe=timeframe, params=params)


def _dict_to_operand(data: Dict[str, Any]) -> Operand:
    t = data.get("type")
    if t == "INDICATOR":
        spec = _dict_to_indicator_spec(data.get("spec") or {})
        return IndicatorOperand(spec)
    if t == "NUMBER":
        value = data.get("value")
        try:
            return NumberOperand(float(value))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise IndicatorAlertError(
                "Invalid numeric operand in expression_json",
            ) from exc
    if t == "FIELD":
        name = data.get("name")
        if not isinstance(name, str):
            raise IndicatorAlertError("Field operand missing name")
        return FieldOperand(name)
    raise IndicatorAlertError("Unknown operand type in expression_json")


def expression_from_dict(data: Dict[str, Any]) -> ExpressionNode:
    t = data.get("type")
    if t == "COMPARISON":
        op = data.get("operator")
        left = _dict_to_operand(data.get("left") or {})
        right = _dict_to_operand(data.get("right") or {})
        if not isinstance(op, str):
            raise IndicatorAlertError("Comparison node missing operator")
        return ComparisonNode(left=left, operator=op, right=right)
    if t == "LOGICAL":
        op = data.get("op")
        children_data = data.get("children") or []
        if not isinstance(op, str) or not isinstance(children_data, list):
            raise IndicatorAlertError("Logical node malformed in expression_json")
        children = [expression_from_dict(child) for child in children_data]
        return LogicalNode(op=op, children=children)
    if t == "NOT":
        child_data = data.get("child") or {}
        return NotNode(child=expression_from_dict(child_data))
    raise IndicatorAlertError("Unknown expression node type in expression_json")


# -----------------------------------------------------------------------------
# Evaluation helpers
# -----------------------------------------------------------------------------


def _iter_indicator_specs(expr: ExpressionNode) -> Iterable[IndicatorSpec]:
    if isinstance(expr, ComparisonNode):
        for op in (expr.left, expr.right):
            if isinstance(op, IndicatorOperand):
                yield op.spec
        return
    if isinstance(expr, NotNode):
        yield from _iter_indicator_specs(expr.child)
        return
    if isinstance(expr, LogicalNode):
        for child in expr.children:
            yield from _iter_indicator_specs(child)


def _indicator_key(spec: IndicatorSpec) -> Tuple[str, str, Tuple[Tuple[str, Any], ...]]:
    params_items = tuple(sorted((str(k), spec.params[k]) for k in spec.params))
    return spec.kind, spec.timeframe, params_items


def _iter_field_names(expr: ExpressionNode) -> Iterable[str]:
    if isinstance(expr, ComparisonNode):
        for op in (expr.left, expr.right):
            if isinstance(op, FieldOperand):
                yield op.name
        return
    if isinstance(expr, NotNode):
        yield from _iter_field_names(expr.child)
        return
    if isinstance(expr, LogicalNode):
        for child in expr.children:
            yield from _iter_field_names(child)


def _compute_indicator_samples_for_expr(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    expr: ExpressionNode,
) -> Dict[Tuple[str, str, Tuple[Tuple[str, Any], ...]], IndicatorSample]:
    specs = list(_iter_indicator_specs(expr))
    by_timeframe: Dict[str, List[IndicatorSpec]] = {}
    for spec in specs:
        by_timeframe.setdefault(spec.timeframe, []).append(spec)

    samples: Dict[Tuple[str, str, Tuple[Tuple[str, Any], ...]], IndicatorSample] = {}
    for timeframe, specs_for_tf in by_timeframe.items():
        candles = _load_candles_for_rule(db, settings, symbol, exchange, timeframe)
        if not candles:
            continue
        for spec in specs_for_tf:
            cond = IndicatorCondition(
                indicator=spec.kind,
                operator="GT",  # operator is ignored by _compute_indicator_sample
                threshold_1=0.0,
                params=dict(spec.params or {}),
            )
            sample = _compute_indicator_sample(candles, cond)
            samples[_indicator_key(spec)] = sample
    return samples


def _compute_field_samples_for_expr(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    expr: ExpressionNode,
) -> Dict[str, IndicatorSample]:
    """Compute snapshot-style field values (e.g., INVESTED, PNL_PCT) for a symbol."""

    field_names = {name.upper() for name in _iter_field_names(expr)}
    if not field_names:
        return {}

    pos = (
        db.query(Position)
        .filter(Position.symbol == symbol, Position.product == "CNC")
        .one_or_none()
    )
    if pos is None:
        return {}

    qty = float(pos.qty)
    avg_price = float(pos.avg_price)
    invested = qty * avg_price

    candles = _load_candles_for_rule(db, settings, symbol, exchange, "1d")
    closes = [float(c["close"]) for c in candles] if candles else []
    last_price = closes[-1] if closes else None
    current_value = qty * last_price if last_price is not None else None

    pnl_pct: Optional[float] = None
    if invested > 0 and current_value is not None:
        pnl_pct = (current_value - invested) / invested * 100.0

    bar_time = candles[-1]["ts"] if candles else None

    samples: Dict[str, IndicatorSample] = {}

    def _put(name: str, value: Optional[float]) -> None:
        if name in field_names:
            samples[name] = IndicatorSample(value, None, bar_time)

    _put("QTY", qty)
    _put("AVG_PRICE", avg_price)
    _put("INVESTED", invested)
    _put("CURRENT_VALUE", current_value)
    _put("PNL_PCT", pnl_pct)

    return samples


def _resolve_operand_value(
    operand: Operand,
    indicator_samples: Dict[
        Tuple[str, str, Tuple[Tuple[str, Any], ...]], IndicatorSample
    ],
    field_samples: Dict[str, IndicatorSample],
) -> Tuple[Optional[float], Optional[float]]:
    if isinstance(operand, NumberOperand):
        return operand.value, operand.value
    if isinstance(operand, IndicatorOperand):
        key = _indicator_key(operand.spec)
        sample = indicator_samples.get(key)
        if sample is None:
            return None, None
        return sample.value, sample.prev_value
    if isinstance(operand, FieldOperand):
        sample = field_samples.get(operand.name.upper())
        if sample is None:
            return None, None
        return sample.value, sample.prev_value
    return None, None


def _evaluate_comparison(
    node: ComparisonNode,
    indicator_samples: Dict[
        Tuple[str, str, Tuple[Tuple[str, Any], ...]], IndicatorSample
    ],
    field_samples: Dict[str, IndicatorSample],
) -> bool:
    op = node.operator.upper()
    left_curr, left_prev = _resolve_operand_value(
        node.left,
        indicator_samples,
        field_samples,
    )
    right_curr, right_prev = _resolve_operand_value(
        node.right,
        indicator_samples,
        field_samples,
    )

    if left_curr is None or (
        right_curr is None and op not in {"CROSS_ABOVE", "CROSS_BELOW"}
    ):
        return False

    if op == "GT":
        return left_curr > float(right_curr)
    if op == "GTE":
        return left_curr >= float(right_curr)
    if op == "LT":
        return left_curr < float(right_curr)
    if op == "LTE":
        return left_curr <= float(right_curr)
    if op == "EQ":
        return left_curr == float(right_curr)
    if op == "NEQ":
        return left_curr != float(right_curr)

    if op in {"CROSS_ABOVE", "CROSS_BELOW"}:
        # For cross operators, both sides should ideally be indicators.
        # When the right side is a NUMBER, treat it as a constant level.
        if left_prev is None:
            return False

        if isinstance(node.right, NumberOperand):
            level = float(node.right.value)
            if op == "CROSS_ABOVE":
                return left_prev <= level < left_curr
            return left_prev >= level > left_curr

        # Indicator vs indicator cross
        if right_curr is None or right_prev is None:
            return False
        if op == "CROSS_ABOVE":
            return left_prev <= right_prev and left_curr > right_curr
        return left_prev >= right_prev and left_curr < right_curr

    # Unknown operator -> treat as non-match
    return False


def evaluate_expression(
    expr: ExpressionNode,
    indicator_samples: Dict[
        Tuple[str, str, Tuple[Tuple[str, Any], ...]], IndicatorSample
    ],
    field_samples: Dict[str, IndicatorSample],
) -> bool:
    if isinstance(expr, ComparisonNode):
        return _evaluate_comparison(expr, indicator_samples, field_samples)
    if isinstance(expr, NotNode):
        return not evaluate_expression(expr.child, indicator_samples, field_samples)
    if isinstance(expr, LogicalNode):
        op = expr.op.upper()
        if op == "AND":
            return all(
                evaluate_expression(child, indicator_samples, field_samples)
                for child in expr.children
            )
        if op == "OR":
            return any(
                evaluate_expression(child, indicator_samples, field_samples)
                for child in expr.children
            )
        raise IndicatorAlertError(f"Unsupported logical operator: {expr.op}")
    raise IndicatorAlertError("Unsupported expression node type")


def evaluate_expression_for_symbol(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    expr: ExpressionNode,
) -> Tuple[bool, Dict[Tuple[str, str, Tuple[Tuple[str, Any], ...]], IndicatorSample]]:
    """Evaluate an expression for a single symbol/exchange.

    Returns a tuple of (matched, samples_by_indicator) where
    samples_by_indicator contains indicator values only; field values are
    used internally for evaluation but are not returned.
    """

    indicator_samples = _compute_indicator_samples_for_expr(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        expr=expr,
    )
    field_samples = _compute_field_samples_for_expr(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        expr=expr,
    )
    if not indicator_samples and not field_samples:
        return False, indicator_samples
    matched = evaluate_expression(expr, indicator_samples, field_samples)
    return matched, indicator_samples


__all__ = [
    "IndicatorSpec",
    "IndicatorOperand",
    "NumberOperand",
    "ComparisonNode",
    "LogicalNode",
    "NotNode",
    "expression_to_dict",
    "expression_from_dict",
    "evaluate_expression_for_symbol",
]
