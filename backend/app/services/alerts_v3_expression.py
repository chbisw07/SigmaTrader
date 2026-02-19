from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import exp, isfinite, log, sqrt
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.market_hours import IST_OFFSET
from app.models import Position
from app.schemas.positions import HoldingRead
from app.services.indicator_alerts import IndicatorAlertError, _load_candles_for_rule

Timeframe = str  # e.g. "1m", "5m", "1h", "1d"


def _now_ist_naive() -> datetime:
    return (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)


def timeframe_to_timedelta(tf: str) -> timedelta:
    tf = (tf or "").strip().lower()
    if tf.endswith("mo"):
        return timedelta(days=int(tf[:-2]) * 30)
    if tf.endswith("y"):
        return timedelta(days=int(tf[:-1]) * 365)
    if tf.endswith("m"):
        return timedelta(minutes=int(tf[:-1]))
    if tf.endswith("h"):
        return timedelta(hours=int(tf[:-1]))
    if tf.endswith("d"):
        return timedelta(days=int(tf[:-1]))
    if tf.endswith("w"):
        return timedelta(days=int(tf[:-1]) * 7)
    raise IndicatorAlertError(f"Unsupported timeframe '{tf}'")


# -----------------------------------------------------------------------------
# AST nodes
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    node_type: str

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class NumberNode(Node):
    value: float

    def __init__(self, value: float) -> None:
        object.__setattr__(self, "node_type", "NUMBER")
        object.__setattr__(self, "value", float(value))

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.node_type, "value": self.value}


@dataclass(frozen=True)
class IdentNode(Node):
    name: str

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "node_type", "IDENT")
        object.__setattr__(self, "name", name)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.node_type, "name": self.name}


@dataclass(frozen=True)
class CallNode(Node):
    name: str
    args: Tuple["ExprNode", ...]

    def __init__(self, name: str, args: Sequence["ExprNode"]) -> None:
        object.__setattr__(self, "node_type", "CALL")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "args", tuple(args))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.node_type,
            "name": self.name,
            "args": [node_to_dict(a) for a in self.args],
        }


@dataclass(frozen=True)
class UnaryNode(Node):
    op: str
    child: "ExprNode"

    def __init__(self, op: str, child: "ExprNode") -> None:
        object.__setattr__(self, "node_type", "UNARY")
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "child", child)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.node_type,
            "op": self.op,
            "child": node_to_dict(self.child),
        }


@dataclass(frozen=True)
class BinaryNode(Node):
    op: str
    left: "ExprNode"
    right: "ExprNode"

    def __init__(self, op: str, left: "ExprNode", right: "ExprNode") -> None:
        object.__setattr__(self, "node_type", "BINARY")
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.node_type,
            "op": self.op,
            "left": node_to_dict(self.left),
            "right": node_to_dict(self.right),
        }


@dataclass(frozen=True)
class ComparisonNode(Node):
    op: str
    left: "ExprNode"
    right: "ExprNode"

    def __init__(self, op: str, left: "ExprNode", right: "ExprNode") -> None:
        object.__setattr__(self, "node_type", "CMP")
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.node_type,
            "op": self.op,
            "left": node_to_dict(self.left),
            "right": node_to_dict(self.right),
        }


@dataclass(frozen=True)
class EventNode(Node):
    op: str
    left: "ExprNode"
    right: "ExprNode"

    def __init__(self, op: str, left: "ExprNode", right: "ExprNode") -> None:
        object.__setattr__(self, "node_type", "EVENT")
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.node_type,
            "op": self.op,
            "left": node_to_dict(self.left),
            "right": node_to_dict(self.right),
        }


@dataclass(frozen=True)
class LogicalNode(Node):
    op: str
    children: Tuple["ExprNode", ...]

    def __init__(self, op: str, children: Sequence["ExprNode"]) -> None:
        object.__setattr__(self, "node_type", "LOGICAL")
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "children", tuple(children))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.node_type,
            "op": self.op,
            "children": [node_to_dict(c) for c in self.children],
        }


@dataclass(frozen=True)
class NotNode(Node):
    child: "ExprNode"

    def __init__(self, child: "ExprNode") -> None:
        object.__setattr__(self, "node_type", "NOT")
        object.__setattr__(self, "child", child)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.node_type, "child": node_to_dict(self.child)}


ExprNode = (
    NumberNode
    | IdentNode
    | CallNode
    | UnaryNode
    | BinaryNode
    | ComparisonNode
    | EventNode
    | LogicalNode
    | NotNode
)


def node_to_dict(node: ExprNode) -> Dict[str, Any]:
    return node.to_dict()


def node_from_dict(data: Dict[str, Any]) -> ExprNode:
    t = data.get("type")
    if t == "NUMBER":
        return NumberNode(float(data.get("value", 0)))
    if t == "IDENT":
        return IdentNode(str(data.get("name", "")))
    if t == "CALL":
        return CallNode(
            str(data.get("name", "")),
            [node_from_dict(a) for a in (data.get("args") or [])],
        )
    if t == "UNARY":
        return UnaryNode(
            str(data.get("op", "")), node_from_dict(data.get("child") or {})
        )
    if t == "BINARY":
        return BinaryNode(
            str(data.get("op", "")),
            node_from_dict(data.get("left") or {}),
            node_from_dict(data.get("right") or {}),
        )
    if t == "CMP":
        return ComparisonNode(
            str(data.get("op", "")),
            node_from_dict(data.get("left") or {}),
            node_from_dict(data.get("right") or {}),
        )
    if t == "EVENT":
        return EventNode(
            str(data.get("op", "")),
            node_from_dict(data.get("left") or {}),
            node_from_dict(data.get("right") or {}),
        )
    if t == "LOGICAL":
        return LogicalNode(
            str(data.get("op", "")),
            [node_from_dict(c) for c in (data.get("children") or [])],
        )
    if t == "NOT":
        return NotNode(node_from_dict(data.get("child") or {}))
    raise IndicatorAlertError(f"Unknown AST node type '{t}'")


def dumps_ast(node: ExprNode) -> str:
    return json.dumps(node_to_dict(node), default=str)


def loads_ast(raw: str) -> ExprNode:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IndicatorAlertError("Invalid AST JSON") from exc
    if not isinstance(data, dict):
        raise IndicatorAlertError("AST JSON must be an object")
    return node_from_dict(data)


# -----------------------------------------------------------------------------
# Metrics (columns/fields) — reused by alerts as operands
# -----------------------------------------------------------------------------


_ALLOWED_METRICS = {
    "TODAY_PNL_PCT",
    "PNL_PCT",
    "MAX_PNL_PCT",
    "DRAWDOWN_PCT",
    "INVESTED",
    "CURRENT_VALUE",
    "QTY",
    "AVG_PRICE",
}


def compute_metric(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    metric: str,
    holding: HoldingRead | None = None,
    allow_fetch: bool = True,
) -> Tuple[Optional[float], Optional[float], Optional[datetime]]:
    # Approximate from positions + daily candles.
    metric = metric.upper()
    if metric not in _ALLOWED_METRICS:
        raise IndicatorAlertError(f"Unknown metric '{metric}'")

    # Prefer live holdings snapshot when available for metrics that should
    # reflect Zerodha's current view (LTP/day-change). This keeps v3 behaviour
    # aligned with the Holdings page and avoids requiring the cached `positions`
    # table to be in sync.
    if holding is not None:
        qty_h = float(holding.quantity)
        avg_h = float(holding.average_price)
        invested_h = qty_h * avg_h
        last_h: float | None = None
        if holding.last_price is not None:
            try:
                last_h = float(holding.last_price)
            except (TypeError, ValueError):
                last_h = None

        if metric == "QTY":
            return qty_h, qty_h, None
        if metric == "AVG_PRICE":
            return avg_h, avg_h, None
        if metric == "INVESTED":
            return invested_h, invested_h, None
        if metric == "CURRENT_VALUE":
            v = qty_h * last_h if last_h is not None else None
            return v, v, None
        if metric == "PNL_PCT" and holding.total_pnl_percent is not None:
            v = float(holding.total_pnl_percent)
            return v, v, None
        if metric == "TODAY_PNL_PCT" and holding.today_pnl_percent is not None:
            v = float(holding.today_pnl_percent)
            return v, v, None

    exch = (exchange or "NSE").upper()
    pos = (
        db.query(Position)
        .filter(
            Position.symbol == symbol,
            Position.exchange == exch,
            Position.product == "CNC",
        )
        .one_or_none()
    )
    if pos is None:
        return None, None, None

    qty = float(pos.qty)
    avg_price = float(pos.avg_price)
    invested = qty * avg_price

    candles = _load_candles_for_rule(
        db, settings, symbol, exchange, "1d", allow_fetch=allow_fetch
    )
    closes = [float(c["close"]) for c in candles] if candles else []
    last_price = closes[-1] if closes else None
    prev_price = closes[-2] if len(closes) >= 2 else None
    bar_time = candles[-1]["ts"] if candles else None

    current_value = qty * last_price if last_price is not None else None
    prev_value = qty * prev_price if prev_price is not None else None
    pnl_pct = None
    pnl_pct_prev = None
    if invested > 0 and current_value is not None:
        pnl_pct = (current_value - invested) / invested * 100.0
    if invested > 0 and prev_value is not None:
        pnl_pct_prev = (prev_value - invested) / invested * 100.0

    today_pnl_pct = None
    today_pnl_pct_prev = None
    if len(closes) >= 2 and closes[-2] != 0:
        today_pnl_pct = (closes[-1] - closes[-2]) / closes[-2] * 100.0
    if len(closes) >= 3 and closes[-3] != 0:
        today_pnl_pct_prev = (closes[-2] - closes[-3]) / closes[-3] * 100.0

    max_pnl_pct = None
    drawdown_pct = None
    max_pnl_pct_prev = None
    drawdown_pct_prev = None
    if avg_price > 0 and closes:
        pnl_series = [(c / avg_price - 1.0) * 100.0 for c in closes]
        max_pnl_pct = max(pnl_series)
        drawdown_pct = pnl_series[-1] - max_pnl_pct
        if len(pnl_series) >= 2:
            prev_series = pnl_series[:-1]
            max_pnl_pct_prev = max(prev_series) if prev_series else None
            drawdown_pct_prev = (
                pnl_series[-2] - max_pnl_pct_prev
                if max_pnl_pct_prev is not None
                else None
            )

    value_map: Dict[str, Optional[float]] = {
        "QTY": qty,
        "AVG_PRICE": avg_price,
        "INVESTED": invested,
        "CURRENT_VALUE": current_value,
        "PNL_PCT": pnl_pct,
        "TODAY_PNL_PCT": today_pnl_pct,
        "MAX_PNL_PCT": max_pnl_pct,
        "DRAWDOWN_PCT": drawdown_pct,
    }
    prev_map: Dict[str, Optional[float]] = {
        "QTY": qty,
        "AVG_PRICE": avg_price,
        "INVESTED": invested,
        "CURRENT_VALUE": prev_value if prev_value is not None else current_value,
        "PNL_PCT": pnl_pct_prev if pnl_pct_prev is not None else pnl_pct,
        "TODAY_PNL_PCT": (
            today_pnl_pct_prev if today_pnl_pct_prev is not None else today_pnl_pct
        ),
        "MAX_PNL_PCT": (
            max_pnl_pct_prev if max_pnl_pct_prev is not None else max_pnl_pct
        ),
        "DRAWDOWN_PCT": (
            drawdown_pct_prev if drawdown_pct_prev is not None else drawdown_pct
        ),
    }

    v = value_map.get(metric)
    return v, prev_map.get(metric), bar_time


# -----------------------------------------------------------------------------
# Series helpers and built-in functions (Phase A)
# -----------------------------------------------------------------------------


@dataclass
class SeriesValue:
    now: Optional[float]
    prev: Optional[float]
    bar_time: Optional[datetime]


_NAN = float("nan")


def _as_optional(v: float | None) -> Optional[float]:
    if v is None or not isfinite(v):
        return None
    return float(v)


def _series_len(values: Sequence[float]) -> int:
    return len(values)


def _align_series(
    a: Sequence[float], b: Sequence[float]
) -> tuple[list[float], list[float]]:
    n = min(len(a), len(b))
    return list(a[:n]), list(b[:n])


def _binop_series(a: Sequence[float], b: Sequence[float], op: str) -> list[float]:
    aa, bb = _align_series(a, b)
    out: list[float] = []
    for x, y in zip(aa, bb, strict=False):
        if not isfinite(x) or not isfinite(y):
            out.append(_NAN)
            continue
        if op == "+":
            out.append(x + y)
        elif op == "-":
            out.append(x - y)
        elif op == "*":
            out.append(x * y)
        elif op == "/":
            out.append(_NAN if y == 0 else x / y)
        else:
            out.append(_NAN)
    return out


def _unary_series(values: Sequence[float], op: str) -> list[float]:
    if op == "-":
        return [(-v if isfinite(v) else _NAN) for v in values]
    return [(_NAN if not isfinite(v) else v) for v in values]


def _sma_series(values: Sequence[float], length: int) -> list[float]:
    n = len(values)
    if length <= 0:
        return [_NAN] * n
    out = [_NAN] * n
    for i in range(n):
        if i + 1 < length:
            continue
        window = values[i - length + 1 : i + 1]
        if any(not isfinite(v) for v in window):
            continue
        out[i] = sum(window) / length
    return out


def _ema_series(values: Sequence[float], length: int) -> list[float]:
    n = len(values)
    if length <= 0:
        return [_NAN] * n
    out = [_NAN] * n
    k = 2.0 / (length + 1.0)

    # Seed on the first window of `length` consecutive finite values so EMA can
    # be composed over series-producing functions (which often have leading NaNs).
    start: Optional[int] = None
    for i in range(length - 1, n):
        window = values[i - length + 1 : i + 1]
        if any(not isfinite(v) for v in window):
            continue
        start = i
        break
    if start is None:
        return out

    ema = sum(values[start - length + 1 : start + 1]) / length
    out[start] = ema
    for i in range(start + 1, n):
        v = values[i]
        if not isfinite(v) or not isfinite(ema):
            ema = _NAN
        else:
            ema = v * k + ema * (1 - k)
        out[i] = ema
    return out


def _rma_series(values: Sequence[float], length: int) -> list[float]:
    """Wilder's RMA (a.k.a. smoothed moving average).

    Semantics (per docs/v3_dsl_semantics_spec.md):
    - Requires `length` periods; first `length-1` bars are missing (NaN).
    - Seed at the first index where a full finite window exists.
    - Subsequent: rma = (prev_rma*(length-1) + value) / length
    """

    n = len(values)
    out = [_NAN] * n
    if length <= 0 or n < length:
        return out

    start: Optional[int] = None
    for i in range(length - 1, n):
        window = values[i - length + 1 : i + 1]
        if any(not isfinite(v) for v in window):
            continue
        start = i
        break
    if start is None:
        return out

    rma = sum(values[start - length + 1 : start + 1]) / length
    out[start] = rma
    for i in range(start + 1, n):
        v = values[i]
        if not isfinite(v) or not isfinite(rma):
            rma = _NAN
        else:
            rma = (rma * (length - 1) + v) / length
        out[i] = rma
    return out


def _rsi_series(values: Sequence[float], length: int) -> list[float]:
    n = len(values)
    out = [_NAN] * n
    if length <= 0 or n < length:
        return out

    gains = [_NAN] * n
    losses = [_NAN] * n
    gains[0] = 0.0
    losses[0] = 0.0
    for i in range(1, n):
        prev = values[i - 1]
        curr = values[i]
        if not isfinite(prev) or not isfinite(curr):
            continue
        delta = curr - prev
        if delta >= 0:
            gains[i] = delta
            losses[i] = 0.0
        else:
            gains[i] = 0.0
            losses[i] = -delta

    avg_g = _rma_series(gains, length)
    avg_l = _rma_series(losses, length)
    for i in range(n):
        g = avg_g[i]
        loss = avg_l[i]
        if not isfinite(g) or not isfinite(loss):
            continue
        if loss == 0:
            out[i] = 100.0
            continue
        rs = g / loss
        out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _stddev_series(values: Sequence[float], length: int) -> list[float]:
    n = len(values)
    out = [_NAN] * n
    if length <= 1:
        return out
    for i in range(n):
        if i + 1 < length:
            continue
        window = values[i - length + 1 : i + 1]
        if any(not isfinite(v) for v in window):
            continue
        mean = sum(window) / length
        var = sum((v - mean) ** 2 for v in window) / max(length - 1, 1)
        out[i] = sqrt(var)
    return out


def _ret_series(values: Sequence[float]) -> list[float]:
    n = len(values)
    out = [_NAN] * n
    for i in range(1, n):
        a = values[i - 1]
        b = values[i]
        if not isfinite(a) or not isfinite(b) or a == 0:
            continue
        out[i] = (b - a) / a * 100.0
    return out


def _atr_series(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], length: int
) -> list[float]:
    n = min(len(highs), len(lows), len(closes))
    if length <= 0 or n < length:
        return [_NAN] * n

    trs: list[float] = [_NAN] * n
    # For i=0 we don't have prev_close. Define prev_close = close so TR reduces to (high-low).
    if n >= 1:
        h0 = highs[0]
        l0 = lows[0]
        c0 = closes[0]
        if all(isfinite(v) for v in (h0, l0, c0)):
            trs[0] = max(h0 - l0, abs(h0 - c0), abs(l0 - c0))

    for i in range(1, n):
        h = highs[i]
        low = lows[i]
        pc = closes[i - 1]
        if any(not isfinite(v) for v in (h, low, pc)):
            continue
        trs[i] = max(h - low, abs(h - pc), abs(low - pc))

    return _rma_series(trs, length)


def _adx_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    length: int,
) -> list[float]:
    """Average Directional Index (ADX), Wilder smoothing.

    Returns a series aligned to input bars, with leading NaNs until enough data
    is available (first ADX typically appears at index 2*length).
    """

    n = min(len(highs), len(lows), len(closes))
    out = [_NAN] * n
    if length <= 0 or n < (2 * length + 1):
        return out

    tr: list[float] = [_NAN] * n
    plus_dm: list[float] = [_NAN] * n
    minus_dm: list[float] = [_NAN] * n
    for i in range(1, n):
        h = highs[i]
        low = lows[i]
        pc = closes[i - 1]
        ph = highs[i - 1]
        pl = lows[i - 1]
        if any(not isfinite(v) for v in (h, low, pc, ph, pl)):
            continue
        tr[i] = max(h - low, abs(h - pc), abs(low - pc))
        up_move = h - ph
        down_move = pl - low
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    sm_tr: list[float] = [_NAN] * n
    sm_pdm: list[float] = [_NAN] * n
    sm_mdm: list[float] = [_NAN] * n

    init_end = length
    init_tr = tr[1 : init_end + 1]
    init_pdm = plus_dm[1 : init_end + 1]
    init_mdm = minus_dm[1 : init_end + 1]
    if any(not isfinite(v) for v in (*init_tr, *init_pdm, *init_mdm)):
        return out

    sm_tr[init_end] = sum(init_tr)
    sm_pdm[init_end] = sum(init_pdm)
    sm_mdm[init_end] = sum(init_mdm)

    for i in range(init_end + 1, n):
        if any(not isfinite(v) for v in (sm_tr[i - 1], sm_pdm[i - 1], sm_mdm[i - 1])):
            continue
        if any(not isfinite(v) for v in (tr[i], plus_dm[i], minus_dm[i])):
            continue
        sm_tr[i] = sm_tr[i - 1] - (sm_tr[i - 1] / length) + tr[i]
        sm_pdm[i] = sm_pdm[i - 1] - (sm_pdm[i - 1] / length) + plus_dm[i]
        sm_mdm[i] = sm_mdm[i - 1] - (sm_mdm[i - 1] / length) + minus_dm[i]

    dx: list[float] = [_NAN] * n
    for i in range(init_end, n):
        st = sm_tr[i]
        if not isfinite(st) or st == 0:
            continue
        pdi = 100.0 * (sm_pdm[i] / st) if isfinite(sm_pdm[i]) else _NAN
        mdi = 100.0 * (sm_mdm[i] / st) if isfinite(sm_mdm[i]) else _NAN
        if not isfinite(pdi) or not isfinite(mdi) or (pdi + mdi) == 0:
            continue
        dx[i] = 100.0 * abs(pdi - mdi) / (pdi + mdi)

    first_adx_idx = 2 * length
    seed_dx = dx[length : first_adx_idx]
    if len(seed_dx) != length or any(not isfinite(v) for v in seed_dx):
        return out

    adx = sum(seed_dx) / length
    out[first_adx_idx] = adx
    for i in range(first_adx_idx + 1, n):
        if not isfinite(adx) or not isfinite(dx[i]):
            adx = _NAN
        else:
            adx = ((adx * (length - 1)) + dx[i]) / length
        out[i] = adx

    return out


def _macd_components_series(
    values: Sequence[float],
    fast: int,
    slow: int,
    signal: int,
) -> tuple[list[float], list[float], list[float]]:
    n = len(values)
    macd = [_NAN] * n
    sig = [_NAN] * n
    hist = [_NAN] * n
    if fast <= 0 or slow <= 0 or signal <= 0 or n == 0:
        return macd, sig, hist

    ema_fast = _ema_series(values, fast)
    ema_slow = _ema_series(values, slow)
    for i in range(n):
        a = ema_fast[i]
        b = ema_slow[i]
        macd[i] = (a - b) if (isfinite(a) and isfinite(b)) else _NAN

    sig = _ema_series(macd, signal)
    for i in range(n):
        m = macd[i]
        s = sig[i]
        hist[i] = (m - s) if (isfinite(m) and isfinite(s)) else _NAN
    return macd, sig, hist


def _supertrend_series(
    *,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    source: Sequence[float],
    length: int,
    multiplier: float,
) -> tuple[list[float], list[float]]:
    """Compute Supertrend line + direction series.

    Contract: docs/v3_dsl_semantics_spec.md (stateful, no lookahead, warmup).

    Implementation notes:
    - Uses ATR(length) with Wilder RMA smoothing.
    - Default source is expected to be hl2 (handled by the caller).
    - Produces NaN (missing) for the first `length-1` bars.
    - Direction: +1 for uptrend, -1 for downtrend.
    """

    n = min(len(highs), len(lows), len(closes), len(source))
    line = [_NAN] * n
    direction = [_NAN] * n
    if length <= 0 or n < length:
        return line, direction

    atr = _atr_series(highs[:n], lows[:n], closes[:n], length)
    final_upper = [_NAN] * n
    final_lower = [_NAN] * n

    for i in range(n):
        a = atr[i]
        src = source[i]
        c = closes[i]
        if not (isfinite(a) and isfinite(src) and isfinite(c)):
            continue

        basic_upper = src + multiplier * a
        basic_lower = src - multiplier * a

        if i == 0:
            final_upper[i] = basic_upper
            final_lower[i] = basic_lower
            continue

        prev_c = closes[i - 1]
        fu_prev = final_upper[i - 1]
        fl_prev = final_lower[i - 1]

        if isfinite(fu_prev) and isfinite(prev_c):
            final_upper[i] = (
                basic_upper
                if (basic_upper < fu_prev or prev_c > fu_prev)
                else fu_prev
            )
        else:
            final_upper[i] = basic_upper

        if isfinite(fl_prev) and isfinite(prev_c):
            final_lower[i] = (
                basic_lower
                if (basic_lower > fl_prev or prev_c < fl_prev)
                else fl_prev
            )
        else:
            final_lower[i] = basic_lower

        if i < length - 1:
            continue

        if i == length - 1 or not isfinite(direction[i - 1]):
            # Deterministic initialization: start in uptrend at the first valid bar.
            direction[i] = 1.0
        else:
            prev_dir = direction[i - 1]
            if prev_dir > 0:
                direction[i] = -1.0 if c < final_lower[i] else 1.0
            else:
                direction[i] = 1.0 if c > final_upper[i] else -1.0

        line[i] = final_lower[i] if direction[i] > 0 else final_upper[i]

    return line, direction


def _obv_series(closes: Sequence[float], volumes: Sequence[float]) -> list[float]:
    n = min(len(closes), len(volumes))
    out = [_NAN] * n
    if n == 0:
        return out
    obv = 0.0
    out[0] = obv
    for i in range(1, n):
        c0 = closes[i - 1]
        c1 = closes[i]
        v = volumes[i]
        if any(not isfinite(x) for x in (c0, c1, v)):
            out[i] = _NAN
            continue
        if c1 > c0:
            obv += v
        elif c1 < c0:
            obv -= v
        out[i] = obv
    return out


def _vwap_series(
    *,
    candles: Sequence[dict[str, Any]],
    prices: Sequence[float],
    volumes: Sequence[float],
) -> list[float]:
    n = min(len(candles), len(prices), len(volumes))
    out = [_NAN] * n
    if n == 0:
        return out
    cum_pv = 0.0
    cum_v = 0.0
    current_day = candles[0]["ts"].date() if candles and candles[0].get("ts") else None
    for i in range(n):
        ts = candles[i].get("ts")
        day = ts.date() if ts is not None else None
        if current_day is None:
            current_day = day
        if day is not None and current_day is not None and day != current_day:
            current_day = day
            cum_pv = 0.0
            cum_v = 0.0
        p = prices[i]
        v = volumes[i]
        if not isfinite(p) or not isfinite(v) or v < 0:
            out[i] = _NAN
            continue
        cum_pv += p * v
        cum_v += v
        out[i] = _NAN if cum_v == 0 else (cum_pv / cum_v)
    return out


def _rolling_window(values: Sequence[float], end: int, length: int) -> List[float]:
    start = max(end - length + 1, 0)
    return list(values[start : end + 1])


def _sma(values: Sequence[float], length: int) -> SeriesValue:
    if length <= 0 or len(values) < length:
        return SeriesValue(None, None, None)
    now_vals = values[-length:]
    now = sum(now_vals) / length
    prev = None
    if len(values) >= length + 1:
        prev_vals = values[-length - 1 : -1]
        prev = sum(prev_vals) / length
    return SeriesValue(now, prev, None)


def _ema(values: Sequence[float], length: int) -> SeriesValue:
    if length <= 0 or len(values) < length:
        return SeriesValue(None, None, None)
    k = 2.0 / (length + 1.0)

    def _compute(slice_vals: Sequence[float]) -> Optional[float]:
        if len(slice_vals) < length:
            return None
        ema = sum(slice_vals[:length]) / length
        for v in slice_vals[length:]:
            ema = v * k + ema * (1 - k)
        return ema

    now = _compute(values)
    prev = _compute(values[:-1]) if len(values) >= length + 1 else None
    return SeriesValue(now, prev, None)


def _rsi(values: Sequence[float], length: int) -> SeriesValue:
    if length <= 0 or len(values) < length:
        return SeriesValue(None, None, None)
    series = _rsi_series(values, length)
    now = _as_optional(series[-1]) if series else None
    prev = _as_optional(series[-2]) if len(series) >= 2 else None
    return SeriesValue(now, prev, None)


def _stddev(values: Sequence[float], length: int) -> SeriesValue:
    if length <= 1 or len(values) < length:
        return SeriesValue(None, None, None)

    def _std(slice_vals: Sequence[float]) -> Optional[float]:
        if len(slice_vals) < length:
            return None
        window = slice_vals[-length:]
        mean = sum(window) / length
        var = sum((v - mean) ** 2 for v in window) / max(length - 1, 1)
        return sqrt(var)

    now = _std(values)
    prev = _std(values[:-1]) if len(values) >= length + 1 else None
    return SeriesValue(now, prev, None)


def _ret(values: Sequence[float]) -> SeriesValue:
    if len(values) < 2:
        return SeriesValue(None, None, None)
    prev_close = values[-2]
    curr_close = values[-1]
    if prev_close == 0:
        return SeriesValue(None, None, None)
    now = (curr_close - prev_close) / prev_close * 100.0
    prev = None
    if len(values) >= 3 and values[-3] != 0:
        prev = (prev_close - values[-3]) / values[-3] * 100.0
    return SeriesValue(now, prev, None)


def _atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], length: int
) -> SeriesValue:
    n = min(len(highs), len(lows), len(closes))
    if length <= 0 or n < length:
        return SeriesValue(None, None, None)
    series = _atr_series(highs[:n], lows[:n], closes[:n], length)
    now = _as_optional(series[-1]) if series else None
    prev = _as_optional(series[-2]) if len(series) >= 2 else None
    return SeriesValue(now, prev, None)


def _roll_agg(values: Sequence[float], length: int, kind: str) -> SeriesValue:
    if length <= 0 or len(values) < length:
        return SeriesValue(None, None, None)

    def _agg(slice_vals: Sequence[float]) -> Optional[float]:
        if len(slice_vals) < length:
            return None
        window = slice_vals[-length:]
        if kind == "MAX":
            return max(window)
        if kind == "MIN":
            return min(window)
        if kind == "SUM":
            return sum(window)
        if kind == "AVG":
            return sum(window) / length
        return None

    now = _agg(values)
    prev = _agg(values[:-1]) if len(values) >= length + 1 else None
    return SeriesValue(now, prev, None)


def _lag(values: Sequence[float], bars: int) -> SeriesValue:
    if bars < 0 or len(values) <= bars:
        return SeriesValue(None, None, None)
    now_idx = -1 - bars
    prev_idx = -2 - bars
    now = values[now_idx] if abs(now_idx) <= len(values) else None
    prev = values[prev_idx] if abs(prev_idx) <= len(values) else None
    return SeriesValue(now, prev, None)


def _roc(values: Sequence[float], length: int) -> SeriesValue:
    if length <= 0 or len(values) <= length:
        return SeriesValue(None, None, None)

    def _roc_at(end_idx: int) -> Optional[float]:
        # end_idx is inclusive index into values
        if end_idx - length < 0:
            return None
        prev_val = values[end_idx - length]
        curr_val = values[end_idx]
        if prev_val == 0:
            return None
        return (curr_val - prev_val) / prev_val * 100.0

    now = _roc_at(len(values) - 1)
    prev = _roc_at(len(values) - 2) if len(values) >= length + 2 else None
    return SeriesValue(now, prev, None)


def _z_score(values: Sequence[float], length: int) -> SeriesValue:
    if length <= 1 or len(values) < length:
        return SeriesValue(None, None, None)

    def _z(slice_vals: Sequence[float]) -> Optional[float]:
        if len(slice_vals) < length:
            return None
        window = slice_vals[-length:]
        mean = sum(window) / length
        var = sum((v - mean) ** 2 for v in window) / max(length - 1, 1)
        std = sqrt(var)
        if std == 0:
            return None
        return (window[-1] - mean) / std

    now = _z(values)
    prev = _z(values[:-1]) if len(values) >= length + 1 else None
    return SeriesValue(now, prev, None)


def _bollinger(values: Sequence[float], length: int, mult: float) -> SeriesValue:
    if length <= 0 or len(values) < length:
        return SeriesValue(None, None, None)

    def _band(slice_vals: Sequence[float]) -> Optional[float]:
        if len(slice_vals) < length:
            return None
        window = slice_vals[-length:]
        mean = sum(window) / length
        if mult == 0:
            return mean
        if length <= 1:
            return None
        var = sum((v - mean) ** 2 for v in window) / max(length - 1, 1)
        std = sqrt(var)
        return mean + mult * std

    now = _band(values)
    prev = _band(values[:-1]) if len(values) >= length + 1 else None
    return SeriesValue(now, prev, None)


class CandleCache:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        symbol: str,
        exchange: str,
        *,
        allow_fetch: bool = True,
    ) -> None:
        self.db = db
        self.settings = settings
        self.symbol = symbol
        self.exchange = exchange
        self.allow_fetch = allow_fetch
        self._candles: Dict[str, list[dict[str, Any]]] = {}

    def candles(self, tf: str) -> list[dict[str, Any]]:
        tf = tf.lower()
        if tf not in self._candles:
            if tf.endswith("w"):
                # Market data service does not currently persist weekly candles.
                # Resample from daily candles in-memory.
                days = (
                    _load_candles_for_rule(
                        self.db,
                        self.settings,
                        self.symbol,
                        self.exchange,
                        "1d",
                        allow_fetch=self.allow_fetch,
                    )
                    or []
                )
                self._candles[tf] = (
                    _resample_weekly(days, weeks=int(tf[:-1] or "1")) if days else []
                )
            else:
                candles = _load_candles_for_rule(
                    self.db,
                    self.settings,
                    self.symbol,
                    self.exchange,
                    tf,  # type: ignore[arg-type]
                    allow_fetch=self.allow_fetch,
                )
                self._candles[tf] = candles or []
        return self._candles[tf]

    def series(self, tf: str, source: str) -> Tuple[list[float], Optional[datetime]]:
        source = source.lower()
        candles = self.candles(tf)
        key = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }.get(source)
        if key is None:
            raise IndicatorAlertError(f"Unsupported source '{source}'")
        values = [float(c[key]) for c in candles] if candles else []
        bar_time = candles[-1]["ts"] if candles else None
        return values, bar_time


# -----------------------------------------------------------------------------
# Evaluation
# -----------------------------------------------------------------------------


BuiltinFn = str

_ALLOWED_BUILTINS: set[str] = {
    # primitives (series by timeframe)
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    "VOLUME",
    "PRICE",  # alias for CLOSE
    # series indicators
    "SMA",
    "EMA",
    "RSI",
    "ATR",
    "STDDEV",
    "RET",
    "OBV",
    "VWAP",
    "ADX",
    "MACD",
    "MACD_SIGNAL",
    "MACD_HIST",
    "SUPERTREND_LINE",
    "SUPERTREND_DIR",
    # rolling
    "MAX",
    "MIN",
    "AVG",
    "SUM",
    # time-series mechanics (Phase B)
    "LAG",
    "ROC",
    "Z_SCORE",
    "BOLLINGER",
    # Explicit cross helpers (Phase C)
    "CROSSOVER",
    "CROSSUNDER",
    "CROSSING_ABOVE",
    "CROSSING_BELOW",
    # math
    "ABS",
    "SQRT",
    "LOG",
    "EXP",
    "POW",
}

_EVENT_ALIASES = {
    "CROSSING_ABOVE": "CROSSES_ABOVE",
    "CROSSING_BELOW": "CROSSES_BELOW",
}


def _as_number(value: SeriesValue) -> Tuple[Optional[float], Optional[float]]:
    return value.now, value.prev


def _coerce_tf(value: ExprNode, *, params: Dict[str, Any]) -> str:
    if isinstance(value, IdentNode):
        raw = value.name.strip()
        key = raw.strip().upper()
        if key in params and isinstance(params[key], str):
            return str(params[key]).strip().strip('"').strip("'")
        return raw.strip().strip('"').strip("'")
    if isinstance(value, NumberNode):
        # allow 1d tokenization as NUMBER+IDENT at higher parser; not here
        return str(int(value.value))
    raise IndicatorAlertError("Timeframe must be an identifier or string literal")


def _eval_series(
    node: ExprNode,
    *,
    cache: CandleCache,
    tf_hint: str,
    params: Dict[str, Any],
) -> Tuple[list[float], Optional[datetime]]:
    """Evaluate a series-producing expression into a numeric series.

    This supports:
    - primitives: open/high/low/close/volume (+ derived `hlc3`)
    - arithmetic on series (+, -, *, /)
    - indicator functions that return series, enabling composition
      (e.g. RSI(SMA(close, 14, "1d"), 14, "1d"))
    """

    tf_hint = (tf_hint or "1d").strip().lower()

    def _len_from(n: ExprNode) -> int:
        if isinstance(n, NumberNode):
            return int(n.value)
        if isinstance(n, IdentNode):
            key = n.name.strip().upper()
            v = params.get(key)
            if isinstance(v, (int, float)) and int(v) > 0:
                return int(v)
            raise IndicatorAlertError(f"Length parameter '{n.name}' must be numeric")
        raise IndicatorAlertError("Length must be a numeric constant")

    def _float_from(n: ExprNode) -> float:
        if isinstance(n, NumberNode):
            return float(n.value)
        if isinstance(n, IdentNode):
            key = n.name.strip().upper()
            v = params.get(key)
            if isinstance(v, (int, float)):
                return float(v)
            raise IndicatorAlertError(f"Value parameter '{n.name}' must be numeric")
        raise IndicatorAlertError("Value must be a numeric constant")

    if isinstance(node, NumberNode):
        candles = cache.candles(tf_hint)
        n = len(candles)
        bar_time = candles[-1]["ts"] if candles else None
        return [float(node.value)] * n, bar_time

    if isinstance(node, IdentNode):
        key = node.name.strip().lower()
        if key in {"open", "high", "low", "close", "volume"}:
            return cache.series(tf_hint, key)
        if key == "hlc3":
            highs, bar_time = cache.series(tf_hint, "high")
            lows, _ = cache.series(tf_hint, "low")
            closes, _ = cache.series(tf_hint, "close")
            n = min(len(highs), len(lows), len(closes))
            out: list[float] = []
            for i in range(n):
                h = highs[i]
                low = lows[i]
                c = closes[i]
                out.append(
                    _NAN
                    if any(not isfinite(v) for v in (h, low, c))
                    else (h + low + c) / 3.0
                )
            return out, bar_time
        raise IndicatorAlertError(f"Unsupported series identifier '{node.name}'")

    if isinstance(node, UnaryNode):
        series, bar_time = _eval_series(
            node.child, cache=cache, tf_hint=tf_hint, params=params
        )
        return _unary_series(series, node.op), bar_time

    if isinstance(node, BinaryNode):
        left, lt = _eval_series(node.left, cache=cache, tf_hint=tf_hint, params=params)
        right, rt = _eval_series(
            node.right, cache=cache, tf_hint=tf_hint, params=params
        )
        return _binop_series(left, right, node.op), (lt or rt)

    if isinstance(node, CallNode):
        fn = node.name.upper()

        if fn in {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}:
            if len(node.args) != 1:
                raise IndicatorAlertError(f"{fn} expects (timeframe)")
            tf = _coerce_tf(node.args[0], params=params).lower()
            return cache.series(tf, fn.lower())

        if fn == "PRICE":
            if len(node.args) == 1:
                tf = _coerce_tf(node.args[0], params=params).lower()
                return cache.series(tf, "close")
            if len(node.args) == 2:
                source = _coerce_tf(node.args[0], params=params).lower()
                tf = _coerce_tf(node.args[1], params=params).lower()
                if source not in {"open", "high", "low", "close"}:
                    raise IndicatorAlertError(
                        "PRICE source must be open/high/low/close"
                    )
                return cache.series(tf, source)
            raise IndicatorAlertError(
                "PRICE expects (timeframe) or (source, timeframe)"
            )

        if fn in {"SMA", "EMA", "RSI", "STDDEV", "MAX", "MIN", "AVG", "SUM"}:
            if len(node.args) not in {2, 3}:
                raise IndicatorAlertError(f"{fn} expects (series, length, timeframe?)")
            length = _len_from(node.args[1])
            tf = (
                _coerce_tf(node.args[2], params=params).lower()
                if len(node.args) == 3
                else tf_hint
            )
            src, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint=tf, params=params
            )
            if fn == "SMA":
                return _sma_series(src, length), bar_time
            if fn == "EMA":
                return _ema_series(src, length), bar_time
            if fn == "RSI":
                return _rsi_series(src, length), bar_time
            if fn == "STDDEV":
                return _stddev_series(src, length), bar_time
            # For rolling aggregations in series context, treat them as
            # SMA-like windows.
            if fn == "MAX":
                out = [_NAN] * len(src)
                for i in range(len(src)):
                    if i + 1 < length:
                        continue
                    window = src[i - length + 1 : i + 1]
                    if any(not isfinite(v) for v in window):
                        continue
                    out[i] = max(window)
                return out, bar_time
            if fn == "MIN":
                out = [_NAN] * len(src)
                for i in range(len(src)):
                    if i + 1 < length:
                        continue
                    window = src[i - length + 1 : i + 1]
                    if any(not isfinite(v) for v in window):
                        continue
                    out[i] = min(window)
                return out, bar_time
            if fn == "SUM":
                out = [_NAN] * len(src)
                for i in range(len(src)):
                    if i + 1 < length:
                        continue
                    window = src[i - length + 1 : i + 1]
                    if any(not isfinite(v) for v in window):
                        continue
                    out[i] = sum(window)
                return out, bar_time
            if fn == "AVG":
                return _sma_series(src, length), bar_time

        if fn == "RET":
            if len(node.args) != 2:
                raise IndicatorAlertError("RET expects (source, timeframe)")
            tf = _coerce_tf(node.args[1], params=params).lower()
            src, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint=tf, params=params
            )
            return _ret_series(src), bar_time

        if fn == "ATR":
            if len(node.args) != 2:
                raise IndicatorAlertError("ATR expects (length, timeframe)")
            length = _len_from(node.args[0])
            tf = _coerce_tf(node.args[1], params=params).lower()
            highs, bar_time = cache.series(tf, "high")
            lows, _ = cache.series(tf, "low")
            closes, _ = cache.series(tf, "close")
            return _atr_series(highs, lows, closes, length), bar_time

        if fn == "ADX":
            if len(node.args) != 2:
                raise IndicatorAlertError("ADX expects (length, timeframe)")
            length = _len_from(node.args[0])
            tf = _coerce_tf(node.args[1], params=params).lower()
            highs, bar_time = cache.series(tf, "high")
            lows, _ = cache.series(tf, "low")
            closes, _ = cache.series(tf, "close")
            return _adx_series(highs, lows, closes, length), bar_time

        if fn == "OBV":
            if len(node.args) != 3:
                raise IndicatorAlertError("OBV expects (close, volume, timeframe)")
            tf = _coerce_tf(node.args[2], params=params).lower()
            closes, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint=tf, params=params
            )
            vols, _ = _eval_series(node.args[1], cache=cache, tf_hint=tf, params=params)
            return _obv_series(closes, vols), bar_time

        if fn in {"MACD", "MACD_SIGNAL", "MACD_HIST"}:
            if len(node.args) not in {4, 5}:
                raise IndicatorAlertError(
                    f"{fn} expects (series, fast, slow, signal, timeframe?)"
                )
            fast = _len_from(node.args[1])
            slow = _len_from(node.args[2])
            signal = _len_from(node.args[3])
            tf = (
                _coerce_tf(node.args[4], params=params).lower()
                if len(node.args) == 5
                else tf_hint
            )
            src, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint=tf, params=params
            )
            macd, sig, hist = _macd_components_series(src, fast, slow, signal)
            if fn == "MACD":
                return macd, bar_time
            if fn == "MACD_SIGNAL":
                return sig, bar_time
            return hist, bar_time

        if fn in {"SUPERTREND_LINE", "SUPERTREND_DIR"}:
            # SUPERTREND_*([source], length, multiplier, [timeframe])
            if len(node.args) not in {2, 3, 4}:
                raise IndicatorAlertError(
                    f"{fn} expects (len, mult, tf?) or (source, len, mult, tf?)"
                )

            idx = 0
            src_node: ExprNode | None = None
            if len(node.args) in {3, 4}:
                # Heuristic: first arg is source if it's not a plain length number.
                if not isinstance(node.args[0], NumberNode):
                    src_node = node.args[0]
                    idx = 1

            length = _len_from(node.args[idx])
            mult = _float_from(node.args[idx + 1])
            tf = (
                _coerce_tf(node.args[idx + 2], params=params).lower()
                if len(node.args) == idx + 3
                else tf_hint
            )

            highs, bar_time = cache.series(tf, "high")
            lows, _ = cache.series(tf, "low")
            closes, _ = cache.series(tf, "close")

            if src_node is None:
                n = min(len(highs), len(lows))
                src = [
                    _NAN
                    if any(not isfinite(v) for v in (highs[i], lows[i]))
                    else (highs[i] + lows[i]) / 2.0
                    for i in range(n)
                ]
            else:
                src, _src_time = _eval_series(src_node, cache=cache, tf_hint=tf, params=params)

            st_line, st_dir = _supertrend_series(
                highs=highs,
                lows=lows,
                closes=closes,
                source=src,
                length=length,
                multiplier=mult,
            )
            if fn == "SUPERTREND_LINE":
                return st_line, bar_time
            return st_dir, bar_time

        if fn == "VWAP":
            if len(node.args) != 3:
                raise IndicatorAlertError("VWAP expects (price, volume, timeframe)")
            tf = _coerce_tf(node.args[2], params=params).lower()
            candles = cache.candles(tf)
            prices, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint=tf, params=params
            )
            vols, _ = _eval_series(node.args[1], cache=cache, tf_hint=tf, params=params)
            return _vwap_series(candles=candles, prices=prices, volumes=vols), bar_time

        if fn in {"CROSSOVER", "CROSSUNDER", "CROSSING_ABOVE", "CROSSING_BELOW"}:
            if len(node.args) != 2:
                raise IndicatorAlertError(f"{fn} expects (a, b)")
            a, bt = _eval_series(
                node.args[0], cache=cache, tf_hint=tf_hint, params=params
            )
            b, _ = _eval_series(
                node.args[1], cache=cache, tf_hint=tf_hint, params=params
            )
            aa, bb = _align_series(a, b)
            out = [0.0] * len(aa)
            is_up = fn in {"CROSSOVER", "CROSSING_ABOVE"}
            for i in range(1, len(out)):
                a0, a1 = aa[i - 1], aa[i]
                b0, b1 = bb[i - 1], bb[i]
                if any(not isfinite(v) for v in (a0, a1, b0, b1)):
                    continue
                if is_up:
                    out[i] = 1.0 if (a0 <= b0 and a1 > b1) else 0.0
                else:
                    out[i] = 1.0 if (a0 >= b0 and a1 < b1) else 0.0
            return out, bt

    raise IndicatorAlertError("Unsupported series expression")


def _eval_numeric(
    node: ExprNode,
    *,
    db: Session,
    settings: Settings,
    cache: CandleCache,
    holding: HoldingRead | None,
    params: Dict[str, Any],
    custom_indicators: Dict[str, Tuple[List[str], ExprNode]],
    allow_fetch: bool,
) -> SeriesValue:
    if isinstance(node, NumberNode):
        return SeriesValue(node.value, node.value, None)

    if isinstance(node, IdentNode):
        name = node.name.upper()
        # Parameter reference (strategies/custom indicators)
        if name in params:
            v = params[name]
            if isinstance(v, SeriesValue):
                return v
            if isinstance(v, bool):
                n = 1.0 if v else 0.0
                return SeriesValue(n, n, None)
            if isinstance(v, (int, float)):
                n = float(v)
                return SeriesValue(n, n, None)
            raise IndicatorAlertError(
                f"Parameter '{node.name}' is not numeric; "
                "cannot use in numeric context."
            )
        # Metric reference
        if name in _ALLOWED_METRICS:
            now, prev, bar_time = compute_metric(
                db,
                settings,
                symbol=cache.symbol,
                exchange=cache.exchange,
                metric=name,
                holding=holding,
                allow_fetch=allow_fetch,
            )
            return SeriesValue(now, prev, bar_time)
        raise IndicatorAlertError(f"Unknown identifier '{node.name}'")

    if isinstance(node, UnaryNode):
        v = _eval_numeric(
            node.child,
            db=db,
            settings=settings,
            cache=cache,
            holding=holding,
            params=params,
            custom_indicators=custom_indicators,
            allow_fetch=allow_fetch,
        )
        if v.now is None or v.prev is None:
            return SeriesValue(None, None, v.bar_time)
        if node.op == "+":
            return v
        if node.op == "-":
            return SeriesValue(-v.now, -v.prev, v.bar_time)
        raise IndicatorAlertError(f"Unsupported unary operator '{node.op}'")

    if isinstance(node, BinaryNode):
        a = _eval_numeric(
            node.left,
            db=db,
            settings=settings,
            cache=cache,
            holding=holding,
            params=params,
            custom_indicators=custom_indicators,
            allow_fetch=allow_fetch,
        )
        b = _eval_numeric(
            node.right,
            db=db,
            settings=settings,
            cache=cache,
            holding=holding,
            params=params,
            custom_indicators=custom_indicators,
            allow_fetch=allow_fetch,
        )
        if a.now is None or a.prev is None or b.now is None or b.prev is None:
            return SeriesValue(None, None, a.bar_time or b.bar_time)
        if node.op == "+":
            return SeriesValue(a.now + b.now, a.prev + b.prev, a.bar_time or b.bar_time)
        if node.op == "-":
            return SeriesValue(a.now - b.now, a.prev - b.prev, a.bar_time or b.bar_time)
        if node.op == "*":
            return SeriesValue(a.now * b.now, a.prev * b.prev, a.bar_time or b.bar_time)
        if node.op == "/":
            if b.now == 0 or b.prev == 0:
                return SeriesValue(None, None, a.bar_time or b.bar_time)
            return SeriesValue(a.now / b.now, a.prev / b.prev, a.bar_time or b.bar_time)
        raise IndicatorAlertError(f"Unsupported binary operator '{node.op}'")

    if isinstance(node, CallNode):
        name = node.name.upper()

        # Custom indicator call
        if name not in _ALLOWED_BUILTINS:
            spec = custom_indicators.get(name)
            if spec is None:
                raise IndicatorAlertError(f"Unknown function '{node.name}'")
            param_names, body = spec
            if len(node.args) != len(param_names):
                raise IndicatorAlertError(f"{name} expects {len(param_names)} args")
            inner_params: Dict[str, SeriesValue] = {}
            for pname, arg in zip(param_names, node.args, strict=False):
                inner_params[pname.upper()] = _eval_numeric(
                    arg,
                    db=db,
                    settings=settings,
                    cache=cache,
                    holding=holding,
                    params=params,
                    custom_indicators=custom_indicators,
                    allow_fetch=allow_fetch,
                )
            return _eval_numeric(
                body,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=inner_params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )

        # Built-ins
        if name in {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}:
            series, bar_time = _eval_series(
                node, cache=cache, tf_hint="1d", params=params
            )
            now = series[-1] if series else None
            prev = series[-2] if len(series) >= 2 else None
            return SeriesValue(now, prev, bar_time)

        if name == "PRICE":
            series, bar_time = _eval_series(
                node, cache=cache, tf_hint="1d", params=params
            )
            now = series[-1] if series else None
            prev = series[-2] if len(series) >= 2 else None
            return SeriesValue(now, prev, bar_time)

        if name == "RET":
            if len(node.args) != 2:
                raise IndicatorAlertError("RET expects (source, timeframe)")
            tf = _coerce_tf(node.args[1], params=params).lower()
            series, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint=tf, params=params
            )
            v = _ret(series)
            v.bar_time = bar_time
            return v

        if name in {"OBV", "VWAP"}:
            # Compute from full series; works for both latest-only and per-bar
            # (in-memory) caches.
            series, bar_time = _eval_series(
                node, cache=cache, tf_hint="1d", params=params
            )
            now = series[-1] if series else None
            prev = series[-2] if len(series) >= 2 else None
            return SeriesValue(_as_optional(now), _as_optional(prev), bar_time)

        if name in {"ADX", "MACD", "MACD_SIGNAL", "MACD_HIST"}:
            series, bar_time = _eval_series(
                node, cache=cache, tf_hint="1d", params=params
            )
            now = series[-1] if series else None
            prev = series[-2] if len(series) >= 2 else None
            return SeriesValue(_as_optional(now), _as_optional(prev), bar_time)

        if name in {"SUPERTREND_LINE", "SUPERTREND_DIR"}:
            series, bar_time = _eval_series(
                node, cache=cache, tf_hint="1d", params=params
            )
            now = series[-1] if series else None
            prev = series[-2] if len(series) >= 2 else None
            return SeriesValue(_as_optional(now), _as_optional(prev), bar_time)

        if name in {"SMA", "EMA", "RSI", "STDDEV", "MAX", "MIN", "AVG", "SUM"}:
            if len(node.args) not in {2, 3}:
                raise IndicatorAlertError(
                    f"{name} expects (series, length, timeframe?)"
                )
            length_val = _eval_numeric(
                node.args[1],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            length = int(length_val.now) if length_val.now is not None else 0
            tf = (
                _coerce_tf(node.args[2], params=params).lower()
                if len(node.args) == 3
                else "1d"
            )
            series, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint=tf, params=params
            )
            if name == "SMA":
                v = _sma(series, length)
            elif name == "EMA":
                v = _ema(series, length)
            elif name == "RSI":
                v = _rsi(series, length)
            elif name == "STDDEV":
                v = _stddev(series, length)
            else:
                v = _roll_agg(series, length, name)
            v.bar_time = bar_time
            return v

        if name == "LAG":
            if len(node.args) != 2:
                raise IndicatorAlertError("LAG expects (src, bars)")
            bars_val = _eval_numeric(
                node.args[1],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            bars = int(bars_val.now) if bars_val.now is not None else -1
            series, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint="1d", params=params
            )
            v = _lag(series, bars)
            v.bar_time = bar_time
            return v

        if name == "ROC":
            if len(node.args) != 2:
                raise IndicatorAlertError("ROC expects (src, len)")
            length_val = _eval_numeric(
                node.args[1],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            length = int(length_val.now) if length_val.now is not None else 0
            series, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint="1d", params=params
            )
            v = _roc(series, length)
            v.bar_time = bar_time
            return v

        if name == "Z_SCORE":
            if len(node.args) != 2:
                raise IndicatorAlertError("Z_SCORE expects (src, len)")
            length_val = _eval_numeric(
                node.args[1],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            length = int(length_val.now) if length_val.now is not None else 0
            series, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint="1d", params=params
            )
            v = _z_score(series, length)
            v.bar_time = bar_time
            return v

        if name == "BOLLINGER":
            if len(node.args) != 3:
                raise IndicatorAlertError("BOLLINGER expects (src, len, mult)")
            length_val = _eval_numeric(
                node.args[1],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            mult_val = _eval_numeric(
                node.args[2],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            length = int(length_val.now) if length_val.now is not None else 0
            mult = float(mult_val.now) if mult_val.now is not None else 0.0
            series, bar_time = _eval_series(
                node.args[0], cache=cache, tf_hint="1d", params=params
            )
            v = _bollinger(series, length, mult)
            v.bar_time = bar_time
            return v

        if name == "ATR":
            if len(node.args) != 2:
                raise IndicatorAlertError("ATR expects (length, timeframe)")
            length_val = _eval_numeric(
                node.args[0],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            length = int(length_val.now) if length_val.now is not None else 0
            tf = _coerce_tf(node.args[1], params=params).lower()
            highs, bar_time = cache.series(tf, "high")
            lows, _ = cache.series(tf, "low")
            closes, _ = cache.series(tf, "close")
            v = _atr(highs, lows, closes, length)
            v.bar_time = bar_time
            return v

        if name in {"CROSSOVER", "CROSSUNDER", "CROSSING_ABOVE", "CROSSING_BELOW"}:
            if len(node.args) != 2:
                raise IndicatorAlertError(f"{name} expects (a, b)")
            mapped = name
            if name == "CROSSING_ABOVE":
                mapped = "CROSSOVER"
            elif name == "CROSSING_BELOW":
                mapped = "CROSSUNDER"
            a = _eval_numeric(
                node.args[0],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            b = _eval_numeric(
                node.args[1],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            bar_time = a.bar_time or b.bar_time
            if a.prev is None or a.now is None or b.prev is None or b.now is None:
                return SeriesValue(None, None, bar_time)
            if mapped == "CROSSOVER":
                now = 1.0 if (a.prev <= b.prev and a.now > b.now) else 0.0
            else:
                now = 1.0 if (a.prev >= b.prev and a.now < b.now) else 0.0
            return SeriesValue(now, 0.0, bar_time)

        if name == "ABS":
            if len(node.args) != 1:
                raise IndicatorAlertError("ABS expects (x)")
            v = _eval_numeric(
                node.args[0],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if v.now is None or v.prev is None:
                return SeriesValue(None, None, v.bar_time)
            return SeriesValue(abs(v.now), abs(v.prev), v.bar_time)

        if name == "SQRT":
            if len(node.args) != 1:
                raise IndicatorAlertError("SQRT expects (x)")
            v = _eval_numeric(
                node.args[0],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if v.now is None or v.prev is None or v.now < 0 or v.prev < 0:
                return SeriesValue(None, None, v.bar_time)
            return SeriesValue(sqrt(v.now), sqrt(v.prev), v.bar_time)

        if name == "LOG":
            if len(node.args) != 1:
                raise IndicatorAlertError("LOG expects (x)")
            v = _eval_numeric(
                node.args[0],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if v.now is None or v.prev is None or v.now <= 0 or v.prev <= 0:
                return SeriesValue(None, None, v.bar_time)
            return SeriesValue(log(v.now), log(v.prev), v.bar_time)

        if name == "EXP":
            if len(node.args) != 1:
                raise IndicatorAlertError("EXP expects (x)")
            v = _eval_numeric(
                node.args[0],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if v.now is None or v.prev is None:
                return SeriesValue(None, None, v.bar_time)
            return SeriesValue(exp(v.now), exp(v.prev), v.bar_time)

        if name == "POW":
            if len(node.args) != 2:
                raise IndicatorAlertError("POW expects (x, y)")
            a = _eval_numeric(
                node.args[0],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            b = _eval_numeric(
                node.args[1],
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=params,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if a.now is None or a.prev is None or b.now is None or b.prev is None:
                return SeriesValue(None, None, a.bar_time or b.bar_time)
            try:
                return SeriesValue(
                    a.now**b.now, a.prev**b.prev, a.bar_time or b.bar_time
                )
            except (OverflowError, ValueError):
                return SeriesValue(None, None, a.bar_time or b.bar_time)

        raise IndicatorAlertError(f"Unsupported function '{name}'")

    raise IndicatorAlertError("Unsupported numeric expression node")


def eval_condition(
    node: ExprNode,
    *,
    db: Session,
    settings: Settings,
    symbol: str,
    exchange: str,
    holding: HoldingRead | None = None,
    params: Optional[Dict[str, Any]] = None,
    custom_indicators: Dict[str, Tuple[List[str], ExprNode]],
    allow_fetch: bool = True,
) -> Tuple[bool, Dict[str, float], Optional[datetime]]:
    """Evaluate a compiled v3 alert condition for a symbol.

    Returns: (matched, snapshot, bar_time)
    """

    cache = CandleCache(db, settings, symbol, exchange, allow_fetch=allow_fetch)
    snapshot: Dict[str, float] = {}
    p = {str(k).strip().upper(): v for k, v in (params or {}).items() if str(k).strip()}

    def _bool(n: ExprNode) -> bool:
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
                params=p,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            right = _eval_numeric(
                n.right,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=p,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if left.now is None or right.now is None:
                return False
            snapshot["LHS"] = float(left.now)
            snapshot["RHS"] = float(right.now)
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
            op = _EVENT_ALIASES.get(n.op.upper(), n.op.upper())
            left = _eval_numeric(
                n.left,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=p,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            right = _eval_numeric(
                n.right,
                db=db,
                settings=settings,
                cache=cache,
                holding=holding,
                params=p,
                custom_indicators=custom_indicators,
                allow_fetch=allow_fetch,
            )
            if op in {"CROSSES_ABOVE", "CROSSES_BELOW"}:
                if left.prev is None or left.now is None:
                    return False
                if isinstance(n.right, NumberNode):
                    level = float(n.right.value)
                    if op == "CROSSES_ABOVE":
                        return left.prev <= level < left.now
                    return left.prev >= level > left.now
                if right.prev is None or right.now is None:
                    return False
                if op == "CROSSES_ABOVE":
                    return left.prev <= right.prev and left.now > right.now
                return left.prev >= right.prev and left.now < right.now

            if op in {"MOVING_UP", "MOVING_DOWN"}:
                if left.prev is None or left.now is None:
                    return False
                # RHS is numeric-only per spec
                if right.now is None:
                    return False
                if left.prev == 0:
                    return False
                change_pct = (left.now - left.prev) / abs(left.prev) * 100.0
                threshold = float(right.now)
                if op == "MOVING_UP":
                    return change_pct >= threshold
                return (-change_pct) >= threshold

            raise IndicatorAlertError(f"Unknown event op '{n.op}'")

        # If the root is numeric, treat non-zero as True (rare; defensive).
        numeric = _eval_numeric(
            n,
            db=db,
            settings=settings,
            cache=cache,
            holding=holding,
            params=p,
            custom_indicators=custom_indicators,
            allow_fetch=allow_fetch,
        )
        return bool(numeric.now)

    ok = _bool(node)
    # Pick a representative bar_time for debug: default to latest completed 1d close
    _, bar_time = cache.series("1d", "close")
    return ok, snapshot, bar_time


__all__ = [
    "ExprNode",
    "NumberNode",
    "IdentNode",
    "CallNode",
    "UnaryNode",
    "BinaryNode",
    "ComparisonNode",
    "EventNode",
    "LogicalNode",
    "NotNode",
    "dumps_ast",
    "loads_ast",
    "eval_condition",
    "timeframe_to_timedelta",
    "_ALLOWED_METRICS",
]


def _resample_weekly(
    candles_1d: list[dict[str, Any]], *, weeks: int = 1
) -> list[dict[str, Any]]:
    if weeks <= 0:
        return []
    if not candles_1d:
        return []

    # Group daily bars by ISO-week. For weeks > 1, coalesce consecutive ISO weeks
    # into buckets of size N (stable, deterministic).
    buckets: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_key: tuple[int, int] | None = None

    def _week_key(ts: datetime) -> tuple[int, int]:
        iso = ts.isocalendar()
        return iso.year, iso.week

    for c in candles_1d:
        ts = c.get("ts")
        if not isinstance(ts, datetime):
            continue
        key = _week_key(ts)
        if current_key is None:
            current_key = key
        if key != current_key:
            if current:
                buckets.append(current)
            current = [c]
            current_key = key
        else:
            current.append(c)
    if current:
        buckets.append(current)

    # Coalesce N ISO-week buckets into larger buckets.
    coalesced: list[list[dict[str, Any]]] = []
    for i in range(0, len(buckets), weeks):
        chunk: list[dict[str, Any]] = []
        for j in range(i, min(i + weeks, len(buckets))):
            chunk.extend(buckets[j])
        if chunk:
            coalesced.append(chunk)

    out: list[dict[str, Any]] = []
    for chunk in coalesced:
        chunk = [c for c in chunk if isinstance(c.get("ts"), datetime)]
        if not chunk:
            continue
        chunk = sorted(chunk, key=lambda c: c["ts"])
        o = float(chunk[0]["open"])
        h = max(float(c["high"]) for c in chunk)
        low = min(float(c["low"]) for c in chunk)
        cl = float(chunk[-1]["close"])
        v = sum(float(c["volume"]) for c in chunk)
        out.append(
            {
                "ts": chunk[-1]["ts"],
                "open": o,
                "high": h,
                "low": low,
                "close": cl,
                "volume": v,
            }
        )
    return out
