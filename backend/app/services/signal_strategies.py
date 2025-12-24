from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AlertDefinition, ScreenerRun
from app.schemas.alerts_v3 import AlertVariableDef
from app.schemas.signal_strategies import (
    SignalStrategyInputDef,
    SignalStrategyOutputDef,
)
from app.services.alerts_v3_compiler import (
    _dsl_allowed_builtins,
    _ensure_numeric_only,
    compile_alert_expression_parts,
    compile_custom_indicators_for_user,
)
from app.services.alerts_v3_expression import (
    _ALLOWED_METRICS,
    CallNode,
    ComparisonNode,
    EventNode,
    ExprNode,
    IdentNode,
    IndicatorAlertError,
    LogicalNode,
    NotNode,
)


def _json_load(raw: str, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, default=str)


def dump_variables(variables: List[AlertVariableDef]) -> str:
    return _json_dump(
        [v.model_dump() if hasattr(v, "model_dump") else v.dict() for v in variables]
    )


def load_variables(raw: str) -> List[AlertVariableDef]:
    data = _json_load(raw, [])
    if not isinstance(data, list):
        return []
    out: List[AlertVariableDef] = []
    for item in data:
        if isinstance(item, dict):
            out.append(AlertVariableDef(**item))
    return out


def dump_inputs(inputs: List[SignalStrategyInputDef]) -> str:
    return _json_dump(
        [i.model_dump() if hasattr(i, "model_dump") else i.dict() for i in inputs]
    )


def load_inputs(raw: str) -> List[SignalStrategyInputDef]:
    data = _json_load(raw, [])
    if not isinstance(data, list):
        return []
    out: List[SignalStrategyInputDef] = []
    for item in data:
        if isinstance(item, dict):
            out.append(SignalStrategyInputDef(**item))
    return out


def dump_outputs(outputs: List[SignalStrategyOutputDef]) -> str:
    return _json_dump(
        [o.model_dump() if hasattr(o, "model_dump") else o.dict() for o in outputs]
    )


def load_outputs(raw: str) -> List[SignalStrategyOutputDef]:
    data = _json_load(raw, [])
    if not isinstance(data, list):
        return []
    out: List[SignalStrategyOutputDef] = []
    for item in data:
        if isinstance(item, dict):
            out.append(SignalStrategyOutputDef(**item))
    return out


def dump_tags(tags: List[str]) -> str:
    cleaned = [t.strip() for t in tags if (t or "").strip()]
    return _json_dump(sorted(set(cleaned)))


def load_tags(raw: str) -> List[str]:
    data = _json_load(raw, [])
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, str):
            t = item.strip()
            if t:
                out.append(t)
    # de-dupe, preserve stable order
    seen = set()
    deduped = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    return deduped


def dump_regimes(regimes: List[str]) -> str:
    """Serialize strategy regimes.

    Regimes are free-form in v1 (e.g., BULL/BEAR/SIDEWAYS, SWING_TRADING,
    DAY_TRADING). We normalize by uppercasing and converting whitespace to
    underscores so UI/search stays consistent.
    """

    import re

    cleaned = [
        re.sub(r"\s+", "_", r.strip().upper()) for r in regimes if (r or "").strip()
    ]
    out: list[str] = []
    seen: set[str] = set()
    for r in cleaned:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", r):
            continue
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return _json_dump(out)


def load_regimes(raw: str) -> List[str]:
    import re

    data = _json_load(raw, [])
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        r = re.sub(r"\s+", "_", item.strip().upper())
        if not r or not re.fullmatch(r"[A-Z][A-Z0-9_]*", r):
            continue
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out


def _walk(expr: ExprNode) -> Iterable[ExprNode]:
    yield expr
    if isinstance(expr, IdentNode):
        return
    if isinstance(expr, CallNode):
        for a in expr.args:
            yield from _walk(a)
        return
    if isinstance(expr, NotNode):
        yield from _walk(expr.child)
        return
    if isinstance(expr, LogicalNode):
        for c in expr.children:
            yield from _walk(c)
        return
    if isinstance(expr, (ComparisonNode, EventNode)):
        yield from _walk(expr.left)
        yield from _walk(expr.right)
        return


def _is_boolean_root(expr: ExprNode) -> bool:
    return isinstance(expr, (LogicalNode, NotNode, ComparisonNode, EventNode))


def _collect_idents(expr: ExprNode) -> Set[str]:
    out: Set[str] = set()
    for n in _walk(expr):
        if isinstance(n, IdentNode):
            out.add(n.name.upper())
    return out


def _collect_calls(expr: ExprNode) -> Set[str]:
    out: Set[str] = set()
    for n in _walk(expr):
        if isinstance(n, CallNode):
            out.add(n.name.upper())
    return out


@dataclass(frozen=True)
class CompiledOutput:
    name: str
    kind: str
    ast: ExprNode
    requires_holdings_metrics: bool
    referenced_params: Set[str]


def validate_strategy_version(
    db: Session,
    *,
    user_id: int,
    inputs: List[SignalStrategyInputDef],
    variables: List[AlertVariableDef],
    outputs: List[SignalStrategyOutputDef],
    dsl_profile: Optional[str],
) -> Tuple[Dict[str, Any], List[CompiledOutput]]:
    if not outputs:
        raise IndicatorAlertError("At least one output is required.")

    custom_indicators = compile_custom_indicators_for_user(
        db, user_id=user_id, dsl_profile=dsl_profile
    )
    allowed_builtins = _dsl_allowed_builtins(dsl_profile)

    raw_vars = [
        v.model_dump() if hasattr(v, "model_dump") else v.dict() for v in variables
    ]

    input_names = {i.name.strip().upper() for i in inputs if (i.name or "").strip()}
    reserved = set(_ALLOWED_METRICS) | allowed_builtins | set(custom_indicators.keys())
    bad_params = sorted(n for n in input_names if n in reserved)
    if bad_params:
        raise IndicatorAlertError(
            f"Invalid parameter name(s): {', '.join(bad_params)} (reserved identifier)."
        )

    compiled: List[CompiledOutput] = []
    any_holdings = False

    for out in outputs:
        expr_text = (out.dsl or "").strip()
        if not expr_text:
            raise IndicatorAlertError(f"Output '{out.name}' DSL cannot be empty.")

        # Reuse alerts v3 compiler for variables substitution + builtin validation.
        ast, _cadence, var_map = compile_alert_expression_parts(
            db,
            user_id=user_id,
            variables=raw_vars,
            condition_dsl=expr_text,
            evaluation_cadence="1d",
            custom_indicators=custom_indicators,
            dsl_profile=dsl_profile,
        )

        # Validate remaining identifiers: they can only be metrics or declared params.
        idents = _collect_idents(ast)
        unknown_params = sorted(
            n for n in idents if (n not in _ALLOWED_METRICS and n not in input_names)
        )
        if unknown_params:
            raise IndicatorAlertError(
                f"Output '{out.name}' references unknown identifier(s): "
                + ", ".join(unknown_params)
                + ". Define them as inputs (parameters) or use a metric/variable."
            )

        if out.kind.upper() == "OVERLAY":
            _ensure_numeric_only(ast, context=f"Output '{out.name}' (OVERLAY)")
        elif out.kind.upper() == "SIGNAL":
            if not _is_boolean_root(ast):
                raise IndicatorAlertError(
                    f"Output '{out.name}' is marked SIGNAL but is not a boolean "
                    "expression. Wrap numeric series in a comparison, e.g. "
                    "`CROSSOVER(a,b) > 0`."
                )
        else:
            raise IndicatorAlertError(f"Unknown output kind '{out.kind}'.")

        requires_holdings = any(n in _ALLOWED_METRICS for n in idents)
        any_holdings = any_holdings or requires_holdings
        compiled.append(
            CompiledOutput(
                name=out.name,
                kind=out.kind.upper(),
                ast=ast,
                requires_holdings_metrics=requires_holdings,
                referenced_params={n for n in idents if n in input_names},
            )
        )

    compatibility = {"requires_holdings_metrics": bool(any_holdings)}
    return compatibility, compiled


def materialize_params(
    *,
    inputs: List[SignalStrategyInputDef],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge input defaults with overrides.

    Returned keys are UPPERCASE to align with IdentNode resolution.
    """

    out: Dict[str, Any] = {}
    for inp in inputs:
        name = (inp.name or "").strip().upper()
        if not name:
            continue
        if inp.default is not None:
            out[name] = inp.default

    for k, v in (overrides or {}).items():
        key = (k or "").strip().upper()
        if not key:
            continue
        out[key] = v

    # Best-effort coercion for basic types (v1).
    for inp in inputs:
        key = (inp.name or "").strip().upper()
        if not key or key not in out:
            continue
        typ = (inp.type or "").strip().lower()
        val = out[key]
        if val is None:
            continue
        try:
            if typ == "number":
                out[key] = float(val)
            elif typ == "bool":
                if isinstance(val, bool):
                    out[key] = val
                elif isinstance(val, str):
                    out[key] = val.strip().lower() in {"1", "true", "yes", "y", "on"}
                else:
                    out[key] = bool(val)
            elif typ == "timeframe":
                out[key] = str(val).strip()
            elif typ == "enum":
                out[key] = str(val).strip()
            else:
                out[key] = str(val)
        except Exception:
            # Keep raw if coercion fails; validation may catch later.
            pass

    return out


def pick_output(
    outputs: List[SignalStrategyOutputDef],
    *,
    name: str,
    require_kind: str | None = None,
) -> SignalStrategyOutputDef:
    wanted = (name or "").strip()
    if not wanted:
        raise IndicatorAlertError("output_name is required.")
    for out in outputs:
        if (out.name or "").strip() == wanted:
            if require_kind and (out.kind or "").upper() != require_kind.upper():
                raise IndicatorAlertError(
                    f"Output '{wanted}' is not of kind {require_kind}."
                )
            return out
    raise IndicatorAlertError(f"Output not found: {wanted}")


def pick_default_signal_output(
    outputs: List[SignalStrategyOutputDef],
) -> SignalStrategyOutputDef:
    for out in outputs:
        if (out.kind or "").upper() == "SIGNAL":
            return out
    raise IndicatorAlertError("Strategy has no SIGNAL outputs.")


def strategy_usage_counts(
    db: Session, *, version_ids: List[int]
) -> Tuple[Dict[int, int], Dict[int, int]]:
    """Return ({version_id: alert_count}, {version_id: screener_count})."""

    if not version_ids:
        return {}, {}

    alert_counts: Dict[int, int] = {vid: 0 for vid in version_ids}
    for vid, cnt in (
        db.query(
            AlertDefinition.signal_strategy_version_id,
            func.count(AlertDefinition.id),
        )
        .filter(AlertDefinition.signal_strategy_version_id.in_(version_ids))  # type: ignore[arg-type]
        .group_by(AlertDefinition.signal_strategy_version_id)
        .all()
    ):
        if vid is not None:
            alert_counts[int(vid)] = int(cnt or 0)

    screener_counts: Dict[int, int] = {vid: 0 for vid in version_ids}
    for vid, cnt in (
        db.query(ScreenerRun.signal_strategy_version_id, func.count(ScreenerRun.id))
        .filter(ScreenerRun.signal_strategy_version_id.in_(version_ids))  # type: ignore[arg-type]
        .group_by(ScreenerRun.signal_strategy_version_id)
        .all()
    ):
        if vid is not None:
            screener_counts[int(vid)] = int(cnt or 0)

    return alert_counts, screener_counts


__all__ = [
    "materialize_params",
    "pick_default_signal_output",
    "pick_output",
    "dump_inputs",
    "dump_outputs",
    "dump_regimes",
    "dump_tags",
    "dump_variables",
    "load_inputs",
    "load_outputs",
    "load_regimes",
    "load_tags",
    "load_variables",
    "strategy_usage_counts",
    "validate_strategy_version",
]
