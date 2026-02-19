from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Sequence

from app.core.config import Settings
from app.services.alerts_v3_expression import (
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
    timeframe_to_timedelta,
)
from app.services.indicator_alerts import IndicatorAlertError

# Reuse v3 indicator implementations to ensure formula parity.
from app.services.alerts_v3_expression import (  # noqa: E402
    _adx_series,
    _atr_series,
    _ema_series,
    _macd_components_series,
    _rsi_series,
    _sma_series,
    _stddev_series,
    _supertrend_series,
    _vwap_series,
)


_NAN = float("nan")


def _is_missing(x: float) -> bool:
    return not math.isfinite(x)


def _strip_tf(raw: str) -> str:
    return str(raw or "").strip().strip('"').strip("'").lower()


def _node_key(node: ExprNode) -> str:
    # Deterministic structural key.
    return dumps_ast(node)


def _effective_timeframe_for_call(node: CallNode, *, default_tf: str) -> str:
    fn = node.name.upper()
    if fn in {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}:
        if len(node.args) == 1 and isinstance(node.args[0], IdentNode):
            return _strip_tf(node.args[0].name) or default_tf
        return default_tf
    if fn == "PRICE":
        if len(node.args) == 1 and isinstance(node.args[0], IdentNode):
            return _strip_tf(node.args[0].name) or default_tf
        if len(node.args) == 2 and isinstance(node.args[1], IdentNode):
            return _strip_tf(node.args[1].name) or default_tf
        return default_tf
    if fn in {"SMA", "EMA", "RSI", "STDDEV", "MAX", "MIN", "AVG", "SUM"}:
        if len(node.args) == 3 and isinstance(node.args[2], IdentNode):
            return _strip_tf(node.args[2].name) or default_tf
        return default_tf
    if fn in {"ATR", "ADX"}:
        if len(node.args) == 2 and isinstance(node.args[1], IdentNode):
            return _strip_tf(node.args[1].name) or default_tf
        return default_tf
    if fn == "RET":
        if len(node.args) == 2 and isinstance(node.args[1], IdentNode):
            return _strip_tf(node.args[1].name) or default_tf
        return default_tf
    if fn in {"OBV", "VWAP"}:
        if len(node.args) == 3 and isinstance(node.args[2], IdentNode):
            return _strip_tf(node.args[2].name) or default_tf
        return default_tf
    if fn in {"MACD", "MACD_SIGNAL", "MACD_HIST"}:
        if len(node.args) == 5 and isinstance(node.args[4], IdentNode):
            return _strip_tf(node.args[4].name) or default_tf
        return default_tf
    if fn in {"SUPERTREND_LINE", "SUPERTREND_DIR"}:
        # ([source], len, mult, [tf]) — if last arg is a TF token treat as timeframe.
        if len(node.args) in {3, 4} and isinstance(node.args[-1], IdentNode):
            cand = _strip_tf(node.args[-1].name)
            if cand and any(cand.endswith(sfx) for sfx in ("m", "h", "d", "w", "mo", "y")):
                return cand
        return default_tf
    return default_tf


@dataclass(frozen=True)
class TimeframeCandles:
    tf: str
    ts: list[datetime]  # candle timestamp (IST-naive); represents bar start in current storage.
    close_ts: list[datetime]  # evaluation timestamp for the bar close.
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]


@dataclass
class V3SeriesEngineLimits:
    max_ast_nodes: int = 2500
    max_call_depth: int = 64
    max_distinct_timeframes: int = 8
    max_lookback_bars: int = 50_000
    timeout_ms: int = 0  # 0 disables wall-clock timeout


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


def _ast_node_count(node: ExprNode) -> int:
    return sum(1 for _ in _walk(node))


def _ast_call_depth(node: ExprNode) -> int:
    def _depth(n: ExprNode) -> int:
        if isinstance(n, (NumberNode, IdentNode)):
            return 0
        if isinstance(n, CallNode):
            return 1 + (max((_depth(a) for a in n.args), default=0))
        if isinstance(n, UnaryNode):
            return _depth(n.child)
        if isinstance(n, BinaryNode):
            return max(_depth(n.left), _depth(n.right))
        if isinstance(n, (ComparisonNode, EventNode)):
            return max(_depth(n.left), _depth(n.right))
        if isinstance(n, LogicalNode):
            return max((_depth(c) for c in n.children), default=0)
        if isinstance(n, NotNode):
            return _depth(n.child)
        return 0

    return _depth(node)


def _align_high_to_base(
    base_close_ts: Sequence[datetime],
    high_close_ts: Sequence[datetime],
) -> list[int]:
    """Return mapping base_idx -> high_idx based on close timestamps.

    Spec rule: choose the most recently CLOSED higher timeframe bar as-of base close.
    """

    out: list[int] = [-1] * len(base_close_ts)
    j = -1
    for i, t in enumerate(base_close_ts):
        while j + 1 < len(high_close_ts) and high_close_ts[j + 1] <= t:
            j += 1
        out[i] = j
    return out


class V3SeriesEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        base: TimeframeCandles,
        other_timeframes: Dict[str, TimeframeCandles],
        limits: V3SeriesEngineLimits,
    ) -> None:
        self.settings = settings
        self.base = base
        self.tfs: Dict[str, TimeframeCandles] = {base.tf: base, **other_timeframes}
        self.limits = limits

        self._start_time = time.monotonic()

        # Precompute alignment maps for all timeframes to base.
        self._align: Dict[str, list[int]] = {base.tf: list(range(len(base.ts)))}
        for tf, data in self.tfs.items():
            if tf == base.tf:
                continue
            # Enforce "lower timeframe access" rule (spec §4.3).
            if timeframe_to_timedelta(tf) < timeframe_to_timedelta(base.tf):
                raise IndicatorAlertError(
                    "Lower timeframe access is not supported in v3 DSL."
                )
            self._align[tf] = _align_high_to_base(base.close_ts, data.close_ts)

        self._tf_cache: Dict[tuple[str, str], list[float]] = {}
        self._base_cache: Dict[str, list[float]] = {}
        self._bool_cache: Dict[str, list[bool]] = {}

    def _check_timeout(self) -> None:
        if not self.limits.timeout_ms:
            return
        elapsed_ms = (time.monotonic() - self._start_time) * 1000.0
        if elapsed_ms > float(self.limits.timeout_ms):
            raise IndicatorAlertError("v3 backtest evaluation timed out")

    def _source_series_tf(self, tf: str, name: str) -> list[float]:
        data = self.tfs.get(tf)
        if data is None:
            raise IndicatorAlertError(f"Unknown timeframe '{tf}'")
        key = name.lower()
        if key == "open":
            return [float(x) for x in data.open]
        if key == "high":
            return [float(x) for x in data.high]
        if key == "low":
            return [float(x) for x in data.low]
        if key == "close":
            return [float(x) for x in data.close]
        if key == "volume":
            return [float(x) for x in data.volume]
        if key == "hlc3":
            n = min(len(data.high), len(data.low), len(data.close))
            out = [_NAN] * n
            for i in range(n):
                h, lo, c = data.high[i], data.low[i], data.close[i]
                out[i] = (h + lo + c) / 3.0 if all(map(math.isfinite, (h, lo, c))) else _NAN
            return out
        if key == "hl2":
            n = min(len(data.high), len(data.low))
            out = [_NAN] * n
            for i in range(n):
                h, lo = data.high[i], data.low[i]
                out[i] = (h + lo) / 2.0 if all(map(math.isfinite, (h, lo))) else _NAN
            return out
        raise IndicatorAlertError(f"Unsupported source '{name}'")

    def _eval_series_tf(self, node: ExprNode, *, tf: str) -> list[float]:
        """Evaluate a numeric series for the given timeframe."""

        k = (tf, _node_key(node))
        cached = self._tf_cache.get(k)
        if cached is not None:
            return cached

        self._check_timeout()

        data = self.tfs[tf]
        n = len(data.ts)

        if isinstance(node, NumberNode):
            out = [float(node.value)] * n
            self._tf_cache[k] = out
            return out

        if isinstance(node, IdentNode):
            out = self._source_series_tf(tf, node.name)
            self._tf_cache[k] = out
            return out

        if isinstance(node, UnaryNode):
            child = self._eval_series_tf(node.child, tf=tf)
            out = [_NAN] * len(child)
            if node.op == "+":
                out = [(_NAN if _is_missing(v) else float(v)) for v in child]
            elif node.op == "-":
                out = [(_NAN if _is_missing(v) else -float(v)) for v in child]
            else:
                raise IndicatorAlertError(f"Unsupported unary operator '{node.op}'")
            self._tf_cache[k] = out
            return out

        if isinstance(node, BinaryNode):
            a = self._eval_series_tf(node.left, tf=tf)
            b = self._eval_series_tf(node.right, tf=tf)
            m = min(len(a), len(b))
            out = [_NAN] * m
            for i in range(m):
                x = a[i]
                y = b[i]
                if _is_missing(x) or _is_missing(y):
                    continue
                if node.op == "+":
                    out[i] = x + y
                elif node.op == "-":
                    out[i] = x - y
                elif node.op == "*":
                    out[i] = x * y
                elif node.op == "/":
                    out[i] = _NAN if y == 0 else x / y
                else:
                    raise IndicatorAlertError(f"Unsupported binary operator '{node.op}'")
            self._tf_cache[k] = out
            return out

        if isinstance(node, CallNode):
            fn = node.name.upper()

            def _len_from(x: ExprNode) -> int:
                if isinstance(x, NumberNode):
                    return int(float(x.value))
                raise IndicatorAlertError("Length must be a numeric constant in backtests")

            def _float_from(x: ExprNode) -> float:
                if isinstance(x, NumberNode):
                    return float(x.value)
                raise IndicatorAlertError("Value must be a numeric constant in backtests")

            if fn in {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}:
                if len(node.args) != 1 or not isinstance(node.args[0], IdentNode):
                    raise IndicatorAlertError(f"{fn} expects (timeframe)")
                arg_tf = _strip_tf(node.args[0].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                out = self._source_series_tf(tf, fn.lower())
                self._tf_cache[k] = out
                return out

            if fn == "PRICE":
                if len(node.args) == 1 and isinstance(node.args[0], IdentNode):
                    arg_tf = _strip_tf(node.args[0].name)
                    if arg_tf != tf:
                        raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                    out = self._source_series_tf(tf, "close")
                    self._tf_cache[k] = out
                    return out
                if (
                    len(node.args) == 2
                    and isinstance(node.args[0], IdentNode)
                    and isinstance(node.args[1], IdentNode)
                ):
                    source = _strip_tf(node.args[0].name)
                    arg_tf = _strip_tf(node.args[1].name)
                    if arg_tf != tf:
                        raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                    out = self._source_series_tf(tf, source)
                    self._tf_cache[k] = out
                    return out
                raise IndicatorAlertError("PRICE expects (timeframe) or (source, timeframe)")

            if fn in {"SMA", "EMA", "RSI", "STDDEV", "MAX", "MIN", "AVG", "SUM"}:
                if len(node.args) not in {2, 3}:
                    raise IndicatorAlertError(f"{fn} expects (series, length, timeframe?)")
                length = _len_from(node.args[1])
                if length > self.limits.max_lookback_bars:
                    raise IndicatorAlertError("Max lookback bars exceeded")
                arg_tf = tf
                if len(node.args) == 3:
                    if not isinstance(node.args[2], IdentNode):
                        raise IndicatorAlertError("Timeframe must be an identifier")
                    arg_tf = _strip_tf(node.args[2].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                src = self._eval_series_tf(node.args[0], tf=tf)
                if fn == "SMA" or fn == "AVG":
                    out = _sma_series(src, length)
                elif fn == "EMA":
                    out = _ema_series(src, length)
                elif fn == "RSI":
                    out = _rsi_series(src, length)
                elif fn == "STDDEV":
                    out = _stddev_series(src, length)
                else:
                    # Rolling aggregations
                    out = [_NAN] * len(src)
                    for i in range(len(src)):
                        if i + 1 < length:
                            continue
                        window = src[i - length + 1 : i + 1]
                        if any(_is_missing(v) for v in window):
                            continue
                        if fn == "MAX":
                            out[i] = max(window)
                        elif fn == "MIN":
                            out[i] = min(window)
                        elif fn == "SUM":
                            out[i] = sum(window)
                self._tf_cache[k] = out
                return out

            if fn == "RET":
                if len(node.args) != 2 or not isinstance(node.args[1], IdentNode):
                    raise IndicatorAlertError("RET expects (source, timeframe)")
                arg_tf = _strip_tf(node.args[1].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                src = self._eval_series_tf(node.args[0], tf=tf)
                out = [_NAN] * len(src)
                for i in range(1, len(src)):
                    a = src[i - 1]
                    b = src[i]
                    if _is_missing(a) or _is_missing(b) or a == 0:
                        continue
                    out[i] = (b - a) / a * 100.0
                self._tf_cache[k] = out
                return out

            if fn == "ATR":
                if len(node.args) != 2 or not isinstance(node.args[1], IdentNode):
                    raise IndicatorAlertError("ATR expects (length, timeframe)")
                length = _len_from(node.args[0])
                if length > self.limits.max_lookback_bars:
                    raise IndicatorAlertError("Max lookback bars exceeded")
                arg_tf = _strip_tf(node.args[1].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                out = _atr_series(self.tfs[tf].high, self.tfs[tf].low, self.tfs[tf].close, length)
                self._tf_cache[k] = out
                return out

            if fn == "ADX":
                if len(node.args) != 2 or not isinstance(node.args[1], IdentNode):
                    raise IndicatorAlertError("ADX expects (length, timeframe)")
                length = _len_from(node.args[0])
                if length > self.limits.max_lookback_bars:
                    raise IndicatorAlertError("Max lookback bars exceeded")
                arg_tf = _strip_tf(node.args[1].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                out = _adx_series(self.tfs[tf].high, self.tfs[tf].low, self.tfs[tf].close, length)
                self._tf_cache[k] = out
                return out

            if fn in {"MACD", "MACD_SIGNAL", "MACD_HIST"}:
                if len(node.args) not in {4, 5}:
                    raise IndicatorAlertError(f"{fn} expects (series, fast, slow, signal, timeframe?)")
                fast = _len_from(node.args[1])
                slow = _len_from(node.args[2])
                siglen = _len_from(node.args[3])
                for ln in (fast, slow, siglen):
                    if ln > self.limits.max_lookback_bars:
                        raise IndicatorAlertError("Max lookback bars exceeded")
                arg_tf = tf
                if len(node.args) == 5:
                    if not isinstance(node.args[4], IdentNode):
                        raise IndicatorAlertError("Timeframe must be an identifier")
                    arg_tf = _strip_tf(node.args[4].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                src = self._eval_series_tf(node.args[0], tf=tf)
                macd, sig, hist = _macd_components_series(src, fast, slow, siglen)
                out = macd if fn == "MACD" else sig if fn == "MACD_SIGNAL" else hist
                self._tf_cache[k] = out
                return out

            if fn in {"OBV", "VWAP"}:
                if len(node.args) != 3 or not isinstance(node.args[2], IdentNode):
                    raise IndicatorAlertError(f"{fn} expects (price, volume, timeframe)")
                arg_tf = _strip_tf(node.args[2].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                prices = self._eval_series_tf(node.args[0], tf=tf)
                vols = self._eval_series_tf(node.args[1], tf=tf)
                if fn == "OBV":
                    out = [_NAN] * min(len(prices), len(vols))
                    obv = 0.0
                    if out:
                        out[0] = 0.0
                    for i in range(1, len(out)):
                        p0 = prices[i - 1]
                        p1 = prices[i]
                        v = vols[i]
                        if any(_is_missing(x) for x in (p0, p1, v)):
                            continue
                        if p1 > p0:
                            obv += v
                        elif p1 < p0:
                            obv -= v
                        out[i] = obv
                    self._tf_cache[k] = out
                    return out
                candles = [
                    {"ts": t, "open": o, "high": h, "low": lo, "close": c, "volume": v}
                    for t, o, h, lo, c, v in zip(
                        self.tfs[tf].ts,
                        self.tfs[tf].open,
                        self.tfs[tf].high,
                        self.tfs[tf].low,
                        self.tfs[tf].close,
                        self.tfs[tf].volume,
                        strict=False,
                    )
                ]
                out = _vwap_series(candles=candles, prices=prices, volumes=vols)
                self._tf_cache[k] = out
                return out

            if fn in {"SUPERTREND_LINE", "SUPERTREND_DIR"}:
                if len(node.args) not in {2, 3, 4}:
                    raise IndicatorAlertError(
                        f"{fn} expects (len, mult, tf?) or (source, len, mult, tf?)"
                    )
                idx = 0
                src_node: ExprNode | None = None
                if len(node.args) in {3, 4} and not isinstance(node.args[0], NumberNode):
                    src_node = node.args[0]
                    idx = 1
                length = _len_from(node.args[idx])
                mult = _float_from(node.args[idx + 1])
                if length > self.limits.max_lookback_bars:
                    raise IndicatorAlertError("Max lookback bars exceeded")
                arg_tf = tf
                if len(node.args) == idx + 3:
                    if not isinstance(node.args[idx + 2], IdentNode):
                        raise IndicatorAlertError("Timeframe must be an identifier")
                    arg_tf = _strip_tf(node.args[idx + 2].name)
                if arg_tf != tf:
                    raise IndicatorAlertError("Mixed timeframes inside series expressions are not supported")
                if src_node is None:
                    src = self._source_series_tf(tf, "hl2")
                else:
                    src = self._eval_series_tf(src_node, tf=tf)
                st_line, st_dir = _supertrend_series(
                    highs=self.tfs[tf].high,
                    lows=self.tfs[tf].low,
                    closes=self.tfs[tf].close,
                    source=src,
                    length=length,
                    multiplier=mult,
                )
                out = st_line if fn == "SUPERTREND_LINE" else st_dir
                self._tf_cache[k] = out
                return out

            if fn in {"ABS", "SQRT", "LOG", "EXP"}:
                if len(node.args) != 1:
                    raise IndicatorAlertError(f"{fn} expects (x)")
                src = self._eval_series_tf(node.args[0], tf=tf)
                out = [_NAN] * len(src)
                for i, v in enumerate(src):
                    if _is_missing(v):
                        continue
                    if fn == "ABS":
                        out[i] = abs(v)
                    elif fn == "SQRT":
                        out[i] = _NAN if v < 0 else math.sqrt(v)
                    elif fn == "LOG":
                        out[i] = _NAN if v <= 0 else math.log(v)
                    else:
                        out[i] = math.exp(v)
                self._tf_cache[k] = out
                return out

            if fn == "POW":
                if len(node.args) != 2:
                    raise IndicatorAlertError("POW expects (x, y)")
                a = self._eval_series_tf(node.args[0], tf=tf)
                b = self._eval_series_tf(node.args[1], tf=tf)
                m = min(len(a), len(b))
                out = [_NAN] * m
                for i in range(m):
                    x, y = a[i], b[i]
                    if _is_missing(x) or _is_missing(y):
                        continue
                    out[i] = math.pow(x, y)
                self._tf_cache[k] = out
                return out

        raise IndicatorAlertError("Unsupported series expression")

    def _align_series_to_base(self, tf: str, series_tf: Sequence[float]) -> list[float]:
        idxs = self._align[tf]
        out = [_NAN] * len(self.base.ts)
        for i, j in enumerate(idxs):
            if j < 0 or j >= len(series_tf):
                continue
            v = float(series_tf[j])
            out[i] = v if math.isfinite(v) else _NAN
        return out

    def eval_numeric_base(self, node: ExprNode, *, default_tf: str) -> list[float]:
        """Evaluate numeric node as a base-timeframe-aligned series."""

        key = _node_key(node)
        cached = self._base_cache.get(key)
        if cached is not None:
            return cached

        self._check_timeout()

        n = len(self.base.ts)
        if isinstance(node, NumberNode):
            out = [float(node.value)] * n
            self._base_cache[key] = out
            return out

        if isinstance(node, IdentNode):
            raise IndicatorAlertError(f"Unknown identifier '{node.name}'")

        if isinstance(node, UnaryNode):
            child = self.eval_numeric_base(node.child, default_tf=default_tf)
            out = [_NAN] * len(child)
            if node.op == "+":
                out = [(_NAN if _is_missing(v) else float(v)) for v in child]
            elif node.op == "-":
                out = [(_NAN if _is_missing(v) else -float(v)) for v in child]
            else:
                raise IndicatorAlertError(f"Unsupported unary operator '{node.op}'")
            self._base_cache[key] = out
            return out

        if isinstance(node, BinaryNode):
            a = self.eval_numeric_base(node.left, default_tf=default_tf)
            b = self.eval_numeric_base(node.right, default_tf=default_tf)
            m = min(len(a), len(b))
            out = [_NAN] * m
            for i in range(m):
                x = a[i]
                y = b[i]
                if _is_missing(x) or _is_missing(y):
                    continue
                if node.op == "+":
                    out[i] = x + y
                elif node.op == "-":
                    out[i] = x - y
                elif node.op == "*":
                    out[i] = x * y
                elif node.op == "/":
                    out[i] = _NAN if y == 0 else x / y
                else:
                    raise IndicatorAlertError(f"Unsupported binary operator '{node.op}'")
            self._base_cache[key] = out
            return out

        if isinstance(node, CallNode):
            call_tf = _effective_timeframe_for_call(node, default_tf=default_tf)
            series_tf = self._eval_series_tf(node, tf=call_tf)
            out = self._align_series_to_base(call_tf, series_tf)
            self._base_cache[key] = out
            return out

        raise IndicatorAlertError("Unsupported numeric expression")

    def eval_bool_base(self, node: ExprNode, *, default_tf: str) -> list[bool]:
        key = _node_key(node)
        cached = self._bool_cache.get(key)
        if cached is not None:
            return cached

        self._check_timeout()

        n = len(self.base.ts)
        if isinstance(node, LogicalNode):
            child_series = [self.eval_bool_base(c, default_tf=default_tf) for c in node.children]
            out = [False] * n
            op = node.op.upper()
            if op == "AND":
                for i in range(n):
                    out[i] = all(cs[i] for cs in child_series)
            elif op == "OR":
                for i in range(n):
                    out[i] = any(cs[i] for cs in child_series)
            else:
                raise IndicatorAlertError(f"Unknown logical op '{node.op}'")
            self._bool_cache[key] = out
            return out

        if isinstance(node, NotNode):
            child = self.eval_bool_base(node.child, default_tf=default_tf)
            out = [not x for x in child]
            self._bool_cache[key] = out
            return out

        if isinstance(node, ComparisonNode):
            left = self.eval_numeric_base(node.left, default_tf=default_tf)
            right = self.eval_numeric_base(node.right, default_tf=default_tf)
            op = node.op.upper()
            out = [False] * min(len(left), len(right))
            for i in range(len(out)):
                a = left[i]
                b = right[i]
                if _is_missing(a) or _is_missing(b):
                    continue
                if op == "GT":
                    out[i] = a > b
                elif op == "GTE":
                    out[i] = a >= b
                elif op == "LT":
                    out[i] = a < b
                elif op == "LTE":
                    out[i] = a <= b
                elif op == "EQ":
                    out[i] = a == b
                elif op == "NEQ":
                    out[i] = a != b
                else:
                    raise IndicatorAlertError(f"Unknown comparison op '{node.op}'")
            self._bool_cache[key] = out
            return out

        if isinstance(node, EventNode):
            op = node.op.upper()
            left = self.eval_numeric_base(node.left, default_tf=default_tf)
            right = self.eval_numeric_base(node.right, default_tf=default_tf)
            out = [False] * min(len(left), len(right))
            if op not in {"CROSSES_ABOVE", "CROSSES_BELOW", "MOVING_UP", "MOVING_DOWN"}:
                raise IndicatorAlertError(f"Unknown event op '{node.op}'")
            for i in range(1, len(out)):
                a0, a1 = left[i - 1], left[i]
                b0, b1 = right[i - 1], right[i]
                if any(_is_missing(v) for v in (a0, a1, b0, b1)):
                    continue
                if op == "CROSSES_ABOVE":
                    out[i] = a0 <= b0 and a1 > b1
                elif op == "CROSSES_BELOW":
                    out[i] = a0 >= b0 and a1 < b1
                elif op in {"MOVING_UP", "MOVING_DOWN"}:
                    if a0 == 0:
                        continue
                    change_pct = (a1 - a0) / abs(a0) * 100.0
                    thr = b1
                    if op == "MOVING_UP":
                        out[i] = change_pct >= thr
                    else:
                        out[i] = (-change_pct) >= thr
            self._bool_cache[key] = out
            return out

        raise IndicatorAlertError("Expected a boolean expression")


def validate_engine_safety(
    expr: ExprNode, *, referenced_timeframes: Sequence[str], limits: V3SeriesEngineLimits
) -> None:
    nodes = _ast_node_count(expr)
    if nodes > limits.max_ast_nodes:
        raise IndicatorAlertError("Max AST nodes exceeded")
    depth = _ast_call_depth(expr)
    if depth > limits.max_call_depth:
        raise IndicatorAlertError("Max call depth exceeded")
    if len(set(referenced_timeframes)) > limits.max_distinct_timeframes:
        raise IndicatorAlertError("Max distinct timeframes exceeded")


__all__ = [
    "TimeframeCandles",
    "V3SeriesEngine",
    "V3SeriesEngineLimits",
    "validate_engine_safety",
]
