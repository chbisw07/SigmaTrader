# SigmaTrader v3 DSL Semantics Specification
Version: 1.0
Status: Canonical Contract
Scope: Screener + Backtest + Portfolio Backtest + Future Live Execution

---

# 1. Purpose

This document defines the formal semantics of the SigmaTrader v3 Strategy DSL.

The v3 DSL is the single canonical language for:

- Screeners
- Alerts
- Strategy backtesting
- Portfolio strategy backtesting
- Live execution (future)

All runtimes MUST adhere to this specification.

---

# 2. Core Design Principles

1. Single source of truth for strategy logic.
2. Deterministic behavior across runtimes.
3. No lookahead bias.
4. Explicit multi-timeframe alignment semantics.
5. Explicit warmup and missing value semantics.
6. Indicator behavior is deterministic and documented.
7. Backtest execution model is stable and documented.

---

# 3. Evaluation Model

## 3.1 Historical Backtest Mode

- Evaluation occurs once per base timeframe bar.
- Evaluation time is the CLOSE of the base timeframe bar.
- Orders generated from a signal are filled at the NEXT bar OPEN (default fill model).
- No intra-bar execution in v1.

## 3.2 Screener Mode

- Evaluates only the most recently CLOSED bar.
- Uses identical indicator and alignment semantics as backtest.

## 3.3 Portfolio Backtest Mode

- Same as historical backtest mode.
- Applied across multiple symbols.
- Portfolio logic is applied after per-symbol signal generation.

---

# 4. Timeframe Semantics

## 4.1 Base Timeframe

The backtest or screener runs on a defined base timeframe (e.g., 15m, 1h, 1d).

All evaluation steps iterate over base timeframe bars.

---

## 4.2 Multi-Timeframe Rule (Critical)

If an expression references a higher timeframe series (e.g., RSI(close,14,"1h") while base is 15m):

The value used at base bar index i MUST be the value of the most recently CLOSED higher timeframe bar as-of the timestamp of base bar i.

Formal Rule:

Let:
- T_base[i] be timestamp of base bar i
- T_high[j] be timestamp of higher timeframe bars

Then:

Use the largest j such that T_high[j] <= T_base[i]

Never use partially formed higher timeframe bars.
Never use future data.

This eliminates lookahead bias.

---

## 4.3 Lower Timeframe Access

Referencing lower timeframe data from a higher base timeframe is NOT supported in v1.

If attempted → runtime error:
"Lower timeframe access is not supported in v3 DSL."

---

# 5. Series Model

All numeric outputs are series indexed by bar.

A series may be:

- float
- int
- bool
- None (missing)

Series are immutable after computation.

Indicators must be computed once per (symbol, timeframe, params) and cached.

---

# 6. Indicator Semantics

## 6.1 Warmup

If an indicator requires N periods:

- For first N-1 bars → return None
- No forward-filling allowed
- No zero substitution allowed

---

## 6.2 Missing Value Propagation

If any operand in arithmetic or comparison is None:

- Arithmetic result = None
- Comparison result = False
- Logical AND/OR:
    - If any operand is None → treat as False

Rationale:
Strategy conditions should not fire during warmup.

---

## 6.3 ATR

ATR must use Wilder's smoothing (RMA).

Definition:

TR = max(
    high - low,
    abs(high - prev_close),
    abs(low - prev_close)
)

ATR = RMA(TR, length)

---

## 6.4 RSI

RSI must use Wilder's smoothing (RMA).

RSI = 100 - (100 / (1 + RS))

RS = RMA(gain, length) / RMA(loss, length)

---

## 6.5 Supertrend

Supertrend must be implemented as built-in stateful indicator.

Parameters:
- length
- multiplier
- source (default hl2)
- timeframe (optional)

Outputs:

SUPERTREND_LINE → float series
SUPERTREND_DIR → int series (+1 uptrend, -1 downtrend)

Definition must be deterministic and documented in code.

Must not rely on future bars.

---

# 7. Boolean & Logical Semantics

Operators:

- >, >=, <, <=
- ==, !=
- AND
- OR
- NOT
- CROSSES_ABOVE
- CROSSES_BELOW

## 7.1 Cross Semantics

CROSSES_ABOVE(A, B) is True at index i if:

A[i-1] <= B[i-1] AND A[i] > B[i]

CROSSES_BELOW(A, B):

A[i-1] >= B[i-1] AND A[i] < B[i]

If any required value is None → False.

---

# 8. Order Execution Semantics (Backtest)

## 8.1 Entry

If entry condition is True at bar i close:

Order is filled at bar i+1 open.

If i is last bar → no fill.

---

## 8.2 Exit

If exit condition True at bar i close:

Position closed at bar i+1 open.

---

## 8.3 Position Model

Single position per symbol in v1.

No pyramiding in v1.

---

## 8.4 Slippage & Commission

Default:
- Slippage = 0
- Commission = 0

Extensible later.

---

# 9. Portfolio Backtest Semantics

1. Signals generated per symbol independently.
2. Orders sorted by timestamp.
3. Portfolio capital updated sequentially.
4. If insufficient capital → order rejected.

---

# 10. Safety Limits

To prevent expression abuse:

- Max AST nodes: configurable
- Max nested function depth: configurable
- Max distinct timeframes: configurable
- Max lookback bars: configurable
- Runtime timeout: configurable

If exceeded → clear runtime error.

---

# 11. Determinism Requirement

Given:
- Same candles
- Same parameters
- Same config

The result MUST be bitwise identical across runs.

No random behavior allowed.

---

# 12. Error Semantics

If expression references:

- Unsupported function → explicit error
- Lower timeframe → explicit error
- Invalid parameter → explicit error

No silent fallback.

---

# 13. Alignment With Screener

Screener evaluation MUST use identical:

- Indicator formulas
- Timeframe alignment rule
- Warmup behavior
- Boolean semantics

Only difference:
- Screener evaluates last closed bar only.

---

# 14. Backward Compatibility

Legacy backtest DSL:

- Must remain operational
- Marked deprecated
- No new features added

v3 DSL becomes canonical.

---

# 15. Future Extensions (Non-Normative)

Possible later additions:

- Intra-bar execution
- Pyramiding
- Short selling
- Lower timeframe aggregation
- Slippage models
- Commission models

These must extend this spec, not contradict it.

---

# End of Specification