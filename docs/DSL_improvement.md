# DSL Improvement Plan – Unified Series & Signals

This note captures the discussion and decisions around evolving the SigmaTrader DSL to a clear, safe “sweet spot” that is powerful for 80–90% use‑cases without becoming PineScript‑level complex.

## Goals

- Provide one **unified mental model** for Alerts V3, Screener V3, and Dashboard Symbol Explorer.
- Make the DSL:
  - expressive enough for most practical strategies,
  - safe and predictable (no general‑purpose programming),
  - efficient to evaluate across universes and time ranges.
- Reuse the existing Alert V3 engine and DSL wherever possible instead of inventing a new one.

## Core Concepts

### 1. Series variables (numeric)

- Variables are **pure numeric series expressions** evaluated over OHLCV data.
- Examples:
  - `SMA14 = SMA(close, 14, "1d")`
  - `OBV1D = OBV(close, volume, "1d")`
  - `VWAP1D = VWAP(hlc3, volume, "1d")`
  - `RSI_VWAP = RSI(VWAP1D, 14, "1d")`
- Each variable produces a **Series<float>**:
  - Alerts/Screener typically consume the **latest value**.
  - Dashboard (Symbol Explorer) uses the **full history** for overlays.
- Variables must be:
  - side‑effect free,
  - independent (no mutation, no state),
  - composable (variables can depend on other variables).

### 2. Signals (boolean)

- Signals are **boolean expressions** built from variables and indicator calls.
- They use:
  - comparisons (`>`, `>=`, `<`, `<=`, `==`, `!=`),
  - logical operators (`AND`, `OR`, `NOT`),
  - event operators for crossings / direction.
- Examples:
  - `signal = SMA14 > SMA50 AND RSI_VWAP > 60`
  - `bull_cross = CROSSING_ABOVE(SMA14, SMA50)`
  - `bear_cross = CROSSING_BELOW(SMA14, SMA50)`
- A signal evaluates to a **Series<bool>**:
  - Alerts/Screener care about `signal[-1]` (latest bar).
  - Dashboard can turn the full series into **markers** on the chart.

### 3. Events and markers

- From a boolean series we derive **events** (marker positions) for charting.
- For crossing‑style signals:
  - Markers show only at **crossover bars**, not on every bar where the boolean is `true`.
  - Example mappings:
    - `CROSSING_ABOVE(a, b)` → green “up” marker.
    - `CROSSING_BELOW(a, b)` → red “down” marker.
- For generic boolean signals (no explicit crossing), we can:
  - either mark **state transitions** (false → true),
  - or use a simpler “TRUE” marker when needed.
- Output contract for charting:
  - series overlays: `Series<float>` for selected variables,
  - markers: `{ ts, kind, text? }[]` derived from signals.

## Evaluation Modes

### 1. Latest‑only mode

**Intended for:**
- Screener V3 (universe scan on demand),
- Alerts V3 (evaluation at bar close per cadence).

**Behavior:**
- For each symbol:
  - compute required variable series once,
  - evaluate the signal on the **latest bar only**,
  - obtain:
    - `value_latest` per variable for debugging / ranking,
    - `signal_latest` for match/trigger.

**Benefits:**
- Keeps Screener and Alerts **fast and scalable** for 1000–2000 symbols.
- Matches their current semantics; existing users don’t see a behavior change.

### 2. Full‑series mode

**Intended for:**
- Dashboard Symbol Explorer overlays and signals,
- future backtesting / visual inspection tools.

**Behavior:**
- For one symbol (or a small number of symbols) and a time range:
  - compute full variable series,
  - compute full boolean series for the signal,
  - derive markers for display.

**Benefits:**
- Enables “view what this DSL actually did over the last N months” directly on the chart.
- Avoids performance issues by limiting full‑series evaluation to a **small symbol set** (typically 1) and a **capped time horizon** (~2 years daily).

## Safety and Boundaries

The DSL is intentionally **not** a general‑purpose programming language.

Forbidden:
- loops (`for`, `while`, etc.),
- recursion,
- arbitrary indexing (`x[-1]`, `x[5]`, etc.),
- user‑defined functions,
- `if/else` or control flow constructs.

Allowed constructs:
- numeric literals,
- variable references,
- arithmetic (`+`, `-`, `*`, `/`),
- comparisons,
- logical operators,
- a limited set of **whitelisted functions**.

### Whitelisted functions (initial surface)

Series indicators:
- `SMA(source, length, timeframe)`
- `EMA(source, length, timeframe)`
- `RSI(source, length, timeframe)`
- `ATR(length, timeframe)`
- `STDDEV(source, length, timeframe)`
- `RET(source, timeframe)` – returns return over the specified timeframe.
- `OBV(close, volume, timeframe)`
- `VWAP(price, volume, timeframe)`

Series primitives:
- `OPEN(timeframe)`
- `HIGH(timeframe)`
- `LOW(timeframe)`
- `CLOSE(timeframe)`
- `VOLUME(timeframe)`
- possibly convenience aliases like `PRICE(timeframe)` or `hlc3`.

Events:
- `CROSSING_ABOVE(a, b)` / `CROSSING_BELOW(a, b)` (names to be aligned with current `CROSSES_ABOVE` / `CROSSOVER` helpers).

This set is:
- rich enough for most trend / momentum / mean‑reversion / volume‑based strategies,
- compact enough to document and support easily.

## Impact by Area

### Screener V3

Role:
- remains a **one‑shot universe filter**.

Changes:
- Under the hood, variables are always treated as **series**, but Screener uses only the **latest value** when:
  - evaluating the signal,
  - filling “Show variable values” columns.
- Condition builder + DSL tabs simply become syntactic sugar for constructing the signal expression.

Benefits:
- Clear semantics: every variable column is “value of series on the latest bar”.
- No change in user flow; just a more solid foundation.

### Alerts V3

Role:
- uses DSL signals to trigger alerts at a chosen **cadence** (e.g., once per `1d` bar).

Changes:
- Each alert:
  - defines variables (series),
  - defines a signal (boolean) using comparisons and event operators.
- Evaluation:
  - at each cadence tick, compute latest values and `signal_latest`,
  - fire the alert only if the event conditions (e.g., crossing) hold at that bar.

Benefits:
- Alerts share exactly the same DSL as Screener and Dashboard.
- Consistent semantics between “screen”, “alert”, and “visualize”.

### Dashboard / Symbol Explorer

Role:
- the **visual** surface for the DSL:
  - overlay variables on price,
  - show signals as markers,
  - inspect performance and coverage.

Changes:
- Uses **full‑series mode**:
  - overlays: pick which variables to plot (price overlay or independent panes),
  - signals: map events to bullish/bearish markers with tooltips.
- Reuses the same variable definitions as Screener/Alerts, so the chart becomes a “live explanation” of why a screener or alert behaves the way it does.

Benefits:
- Strong debugging / exploration workflow:
  - prototype expressions in Symbol Explorer,
  - lift them into Screener and Alerts once they look promising.

## Summary

- The DSL will be:
  - **Series‑oriented** (variables as Series<float>),
  - **Signal‑driven** (boolean Series<bool> with events),
  - **Mode‑aware** (latest‑only vs full‑series),
  - **Safe** (strict whitelist, no general control flow).
- Screener, Alerts, and Dashboard continue to serve their current roles, but all share:
  - the **same indicator vocabulary**,
  - the **same semantics** for variables and signals,
  - and a clear evaluation contract that makes it easy to extend safely in future.

