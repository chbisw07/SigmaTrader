# Alerts Refactor v3 — Indicator‑First Alerts over Universes (Implementation Reference)

This document merges:
- `~/Desktop/alerts_refactor_v2.md` (detailed wizard wireframes + DSL + custom indicators), and
- `docs/refactoring_alerts.md` (universe‑scoped alert thesis + semantics + migration framing),

into a single, cohesive reference that should be used for implementation and the refactor.

---

## 1) Purpose & scope

We want an alerts system that is:

- TradingView‑like to use (simple, guided, readable).
- Powerful enough for multi‑timeframe + crossovers + column/metric comparisons.
- Bulk‑native by design (an alert monitors a **universe**).
- Safe (no arbitrary code execution).

This refactor covers:
- Alert definition UX (create/edit).
- The expression model + DSL representation.
- Custom indicator definition UX + constraints.
- Required semantics (crossing/moving/missing‑data/multi‑TF).

Out of scope for this document (covered elsewhere):
- Runtime execution plumbing details (workers, queue internals, broker routing).
- Strategy-level automation beyond per-alert templates (global risk controls, portfolio-level limits).

---

## 2) The mental model (the “loop”)

You highlighted the duality:
- multiple alerts per symbol, vs
- one alert over many symbols

The refactor resolves this by making the **alert the actor** and moving the loop inside the engine.

### 2.1 Actor model

An alert runs over its target set:

```
for each Alert A:
  symbols = resolve(A.target)   // symbol or universe
  for each symbol S in symbols:
    if evaluate(A.condition, S) is true:
      emit AlertEvent(A, S, snapshot)
```

Implications:
- Bulk is free: a single alert can cover holdings or a group.
- Multiple alerts per symbol becomes natural: multiple alert actors can overlap on the same symbols.

---

## 3) Core entities

### 3.1 Universe

A **Universe** is a set of symbols. Initially:

- `Holdings (Zerodha)` — dynamic membership
- `Group: t1 / famous5 / …` — dynamic membership

Later (optional):
- watchlists, indices, screener outputs, portfolios/baskets

### 3.2 Alert

An **Alert** is a persisted object with:

- `name`
- `enabled`
- `target`:
  - `SYMBOL(symbol, exchange?)`, or
  - `UNIVERSE(kind, id)` where kind is `HOLDINGS` or `GROUP`
- `variables` (optional): local variable definitions (indicator aliases)
- `condition`: boolean expression (see section 5)
- `trigger_mode`: `ONCE`, `ONCE_PER_BAR`, `EVERY_TIME` (+ optional throttle)
- `time_constraints`:
  - optional market hours gating
  - optional expiry

Alerts always produce `AlertEvent`s for audit/debugging. Additionally, alerts may carry an optional **action**:
- `ALERT_ONLY` (default): current behavior, no orders are created.
- `BUY` / `SELL`: attach a symbol‑free trade template (see section 10) that turns each per‑symbol trigger into an order intent routed to the manual/auto queue.

### 3.3 Indicator catalog (decoupled)

Indicators are not “alerts”; they are reusable computations.

- Built‑in indicators: RSI, SMA, EMA, ATR, VWAP, PERF%, VOLUME, etc.
- Primitives: OHLCV (open/high/low/close/volume)
- Custom indicators (user‑defined compositions) — see section 7.

The UI should have an **Indicators** area for discoverability and governance:
- enable/disable indicator kinds
- create/edit custom indicators

### 3.4 Metrics (columns / fields)

Alerts must be able to compare “grid metrics” too (like the screener):

Examples:
- `TODAY_PNL_PCT`
- `PNL_PCT`
- `INVESTED`
- `CURRENT_VALUE`
- `QTY`
- `AVG_PRICE`
- `DRAWDOWN_PCT`, `MAX_PNL_PCT`, etc.

Metrics are operands in the expression system, same as indicators/variables/constants.

### 3.5 AlertEvent (history)

An `AlertEvent` is an immutable record created when an alert triggers for a symbol.

Minimum fields:
- `alert_id`, `alert_name`
- `symbol`, `exchange`
- `triggered_at`
- `reason` (serialized condition summary)
- `snapshot` (values used to evaluate variables/metrics)

This is critical for trust and debugging (“why did this fire?”).

---

## 4) UX design (wireframes)

### 4.1 Navigation

```
Alerts
------------------------------------------------
Tabs: [ Alerts ] [ Indicators ] [ Events ]
```

- Alerts: list/create/edit/enable/disable alerts.
- Indicators: manage built‑ins visibility + create custom indicators.
- Events: audit trail of triggers with filters.

### 4.2 Alerts list page

```
+---------------------------------------------------------------+
|  ALERTS                                                       |
+---------------------------------------------------------------+
| [ + CREATE ALERT ]                                            |
+---------------------------------------------------------------+
| Name: RSI Oversold 1H on Holdings                             |
| Target: Universe: Holdings (Zerodha)                          |
| Condition: (RSI_1H_14 < 30 AND PRICE_1D > SMA_1D_200)          |
| Status: Enabled     Last Trigger: 2025-01-15 10:32             |
| [ Edit ] [ Disable ] [ Delete ]                               |
|---------------------------------------------------------------|
| Name: Breakout with Volume Spike                              |
| Target: Symbol: INFY / NSE                                     |
| Condition: SMA_1D_20 CROSSES_ABOVE SMA_1D_50 AND VOL > 2*AVG   |
| Status: Disabled    Last Trigger: None                         |
| [ Edit ] [ Enable ] [ Delete ]                                |
+---------------------------------------------------------------+
```

### 4.3 Create/Edit alert wizard

#### Step 1 — Target & meta

```
+---------------------------------------------------------------+
| CREATE ALERT (1/4)                                            |
+---------------------------------------------------------------+
| Alert Name: [____________________________________________]    |
|                                                               |
| Target:                                                       |
| (•) Universe   Universe: [Holdings (Zerodha) v]                |
|     Preview: 23 symbols                                       |
| ( ) Symbol     Symbol:   [INFY v]  Exchange: [NSE v]           |
|                                                               |
| Action: [ Alert only v ]  (Alert only / Buy / Sell)            |
|                                                               |
| Options:                                                      |
| [ ] Only evaluate during market hours                         |
| [ ] Alert expires on: [ 2025-03-01 15:30 ]                     |
|                                                               |
|                               [ Next → ]                      |
+---------------------------------------------------------------+
```

Notes:
- Universe is the primary bulk mechanism.
- If the user starts from selected rows in a grid, the UI should **strongly guide**
  “Create group from selection” (so alerts remain symbol/universe‑scoped and stay
  consistent with the mental model).

#### Step 2 — Variables (local indicator variables)

Variables provide readable aliases for indicator computations:

```
+---------------------------------------------------------------+
| CREATE ALERT (2/4) — Variables                                |
+---------------------------------------------------------------+
| [ + Add Variable ]                                            |
|                                                               |
| Name        | Type      | OHLCV | Bars | Timeframe | Advanced  |
|---------------------------------------------------------------|
| RSI_1H_14    | RSI       | Close | 14  | 1h        | (...)     |
| SMA_1D_50    | SMA       | Close | 50  | 1d        | (...)     |
| PRICE_1D     | PRICE     | Close |  -  | 1d        | (...)     |
| TODAY_PNL    | METRIC    |  -    |  -  |  -        | (...)     |
|                                                               |
|                    [ Back ]   [ Next → ]                      |
+---------------------------------------------------------------+
```

Notes:
- Variables may reference:
  - indicators (RSI/SMA/EMA/ATR/…)
  - OHLCV primitives (PRICE, VOLUME)
  - metrics (TODAY_PNL_PCT, PNL_PCT, …) as “Metric variables” for readability
  - custom indicators (from Indicators tab)
- Variables are alert‑local in Phase 1; later they can be promoted to reusable templates.
- UI rule: for primitives like `PRICE` / `VOLUME`, the `Bars/Length` input is not applicable
  and should be hidden/disabled to avoid confusion.

#### Step 3 — Condition builder (screener‑like)

Condition builder supports:
- compare operand to value OR operand to operand
- AND/OR joins
- event operators (crossing/moving)
- optional advanced grouping later

```
+---------------------------------------------------------------+
| CREATE ALERT (3/4) — Condition Builder                         |
+---------------------------------------------------------------+
| Match mode: (•) All conditions (AND)   ( ) Any (OR)            |
|                                                               |
| LHS            | Operator           | RHS                       |
|---------------------------------------------------------------|
| RSI_1H_14      | <                  | 30                        |
| SMA_1D_20      | CROSSES_ABOVE      | SMA_1D_50                 |
| TODAY_PNL_PCT  | >                  | 5                         |
|                                                               |
| [ + Add condition ]                                            |
|                                                               |
| Expression preview (read‑only):                                |
| (RSI_1H_14 < 30) AND (SMA_1D_20 CROSSES_ABOVE SMA_1D_50)        |
|     AND (TODAY_PNL_PCT > 5)                                    |
|                                                               |
|                    [ Back ]   [ Next → ]                      |
+---------------------------------------------------------------+
```

#### Step 4 — Trigger settings

```
+---------------------------------------------------------------+
| CREATE ALERT (4/4) — Trigger Settings                          |
+---------------------------------------------------------------+
| Trigger mode (per symbol):                                     |
| (•) ONCE                                                      |
| ( ) ONCE_PER_BAR                                              |
| ( ) EVERY_TIME     Throttle: once per [ 15 ] minutes           |
|                                                               |
| Test (optional): [Run condition on last bar]                   |
| INFY → FALSE (RSI_1H_14=44.3, TODAY_PNL_PCT=0.8)               |
| TCS  → TRUE  (RSI_1H_14=28.2, TODAY_PNL_PCT=5.4)               |
|                                                               |
|                    [ Back ]   [ Save Alert ]                   |
+---------------------------------------------------------------+
```

#### Optional — Buy/Sell template tab (when Action = BUY/SELL)

When the user chooses `BUY` or `SELL` in Step 1, the editor should expose an additional tab alongside the condition editor:

```
Tabs: [ Condition ] [ Buy template ]
```

The template tab should look and behave like the existing Holdings buy/sell dialog, with these deliberate differences:
- No symbol header (symbol is resolved at trigger time).
- No BUY/SELL toggle (side is fixed by `Action = BUY/SELL`).
- No `% of portfolio` sizing option in the template.

Template fields (Phase B):
- `submit_mode`: `MANUAL` (review in queue) or `AUTO` (send now)
- `execution_target`: `LIVE` or `PAPER`
- Position sizing (radio): `QTY` / `AMOUNT` / `% of position`
  - Non-selected sizing inputs stay blank (switching modes clears the other inputs).
- Order entry: `order_type`, `price` (disabled for MARKET/SL-M), optional `trigger_price` (for SL*/GTT)
- `product`: `CNC` / `MIS`
- Optional follow-ups: bracket/follow-up GTT (MTP%), and `gtt` (LIMIT only)

### 4.4 Indicators tab (custom indicators)

```
+---------------------------------------------------------------+
| INDICATORS                                                    |
+---------------------------------------------------------------+
| Built‑ins (enable/disable): RSI, SMA, EMA, ATR, VWAP, ...      |
|                                                               |
| Custom indicators                                              |
| [ + Create Custom Indicator ]                                  |
|---------------------------------------------------------------|
| Name            | Params            | Timeframes | Enabled     |
| SWING_SCORE_1D  | src,len_atr,len_v | 1d         | ✓           |
| VALUE_SCORE     | src,window        | 1d         | ✓           |
+---------------------------------------------------------------+
```

Custom indicator creation is described in section 7.

---

## 5) Expression model (what users build)

Alerts “only have conditionals”. Those conditionals are represented and stored as a DSL expression under the hood.

### 5.1 Operands

An operand can be:

1) **Constant**
   - numeric (e.g. `30`, `-5`, `500`)

2) **Variable**
   - a named alias defined in Step 2 (e.g. `RSI_1H_14`)

3) **Metric / column**
   - holdings/universe metrics like `TODAY_PNL_PCT`, `PNL_PCT`, `INVESTED`, etc.
   - these may be referenced directly or via metric variables

4) **Inline function call** (optional, advanced)
   - e.g. `RSI(close, 14, "1h")` (TradingView‑style)
   - in Phase 1, users may not type this; UI still generates it.

Comparisons must support:
- operand vs constant
- operand vs operand

### 5.2 Operators (canonical set + aliases)

#### 5.2.1 Relational
- `<, <=, >, >=, ==, !=`

#### 5.2.2 Event operators
We standardize canonical tokens:
- `CROSSES_ABOVE`, `CROSSES_BELOW`
- `MOVING_UP`, `MOVING_DOWN`

Aliases accepted by parser (for user friendliness / backward compatibility):
- `CROSSING_ABOVE` → `CROSSES_ABOVE`
- `CROSSING_BELOW` → `CROSSES_BELOW`

### 5.3 Combining conditions

Conditions combine with:
- `AND`
- `OR`
- (optional later) `NOT` and parentheses/grouping UI

Phase 1 UI can use a flat list + “match mode” (AND/OR) while still storing a canonical DSL string.

---

## 6) Semantics & evaluation rules (must be explicit)

This section defines how comparisons and event operators work so results are predictable and trusted.

### 6.1 Missing data

Safe default:
- if any required operand cannot be computed for a symbol → the condition evaluates to **false** for that symbol.

In “Test on last bar”, show missing data reasons (recommended):
- “SMA_1D_200 requires 200 bars; only 120 available”

### 6.2 CROSSES_ABOVE / CROSSES_BELOW

Let `A_now`, `A_prev` be current/previous values for the LHS series; similarly for RHS if series.

- `A CROSSES_ABOVE B` is true when:
  - `A_prev <= B_prev` AND `A_now > B_now`
- `A CROSSES_BELOW B` is true when:
  - `A_prev >= B_prev` AND `A_now < B_now`

If RHS is a constant number:
- treat `B_prev == B_now == constant`.

### 6.3 MOVING_UP / MOVING_DOWN

Recommended default semantics: percent change over the last bar:

- `A MOVING_UP x` is true when:
  - `((A_now - A_prev) / abs(A_prev)) * 100 >= x`
- `A MOVING_DOWN x` is true when:
  - `((A_prev - A_now) / abs(A_prev)) * 100 >= x`

RHS for MOVING operators:
- Numeric constant `x` only (simple + unambiguous).

### 6.4 Multi‑timeframe evaluation policy

An alert may reference variables at different timeframes (e.g. `RSI(1h)` AND `SMA(1d)`).

Policy (confirmed: per‑alert cadence, with completed bars):

1) Each alert has an explicit `evaluation_cadence` (timeframe) that determines when it evaluates.
   - Default: the **smallest timeframe referenced** by the alert’s variables/functions.
   - UI should allow overriding cadence explicitly (advanced setting).
2) On each evaluation tick, for each symbol and each referenced timeframe:
   - use the latest **completed** candle/bar for that timeframe
   - use the previous completed candle for `_prev`
3) Event operators (cross/move) use `now/prev` in the timeframe of the operand.
4) If a referenced timeframe has not advanced since last evaluation, its `now/prev` remain unchanged.
   - This is expected; the condition may still change due to other operands evaluated on smaller timeframes.

---

## 7) Variables and indicator definitions

### 7.1 Variable definition schema

You want variable definitions like:

```
<name> <indicator> <OHLCV_value> <bars> <timeframe>
RSI__close_14_1h RSI C 14 1h
```

We model each variable as:
- `name`: string (unique within alert)
- `kind`: indicator kind (RSI/SMA/EMA/ATR/VWAP/PRICE/VOLUME/METRIC/CUSTOM)
- `params`:
  - `source`: OHLCV series (`open|high|low|close|volume`) for series‑based indicators
  - `length` or `window`: integer lookback (as applicable)
  - `timeframe`: timeframe string for series‑based indicators
  - custom indicator params when `kind=CUSTOM`

Notes:
- `PRICE` and `VOLUME` are primitives (they can still accept `timeframe` + `source`).
- For `PRICE` / `VOLUME`, `length/bars` does not apply; the UI must not present it as required.
- Metrics (like `TODAY_PNL_PCT`) do not require timeframe/ohlcv; they resolve from holdings data and/or computed fields.

### 7.2 Custom indicators

Custom indicators are user‑defined indicator functions that can be used like built‑ins.

A Custom Indicator:
- has a name (function id)
- has typed parameters (e.g. `src`, `len_atr`, `len_vol`)
- defines a formula using a restricted expression language (arithmetic + allowed functions)
- returns a numeric value

#### 7.2.1 Custom indicator creation UX

```
Create Custom Indicator
------------------------------------------------
Name:        [ SWING_SCORE_1D ]
Description: [ Measures swinginess of price ]

Parameters:
src      : price_series  default=close
len_atr  : int           default=14
len_vol  : int           default=20

Formula (builder):
ATR(src, len_atr, "1d") / PRICE("1d") * 100
  + StdDev(returns(src, "1d"), len_vol) * 100

[Validate] [Save]
```

#### 7.2.2 Safety constraints

Required guardrails:
- no recursion (A cannot call A)
- bounded function set (see below)
- bounded depth/size of expression
- deterministic evaluation (no I/O, no external data)
- timeouts and caching during evaluation

Canonical function names should be uppercase in storage (UI can show friendly labels and
accept aliases like `StdDev` → `STDDEV`, `returns` → `RET`).

##### A) MVP surface (initial allowed set)
Allowed:
- Primitives: `OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`
- Series: `SMA`, `EMA`, `RSI`, `ATR`, `STDDEV`, `RET`
- Rolling functions: `MAX`, `MIN`, `AVG`, `SUM`
- Arithmetic: `+ - * /` and parentheses

Enables:
- swing score, trend score, normalized volatility, ATR‑percent bands, multi‑indicator blends.

##### B) Time‑series mechanics (add next)
Add:
- `LAG(src, bars)`
- `ROC(src, len)`
- `Z_SCORE(src, len)`
- `BOLLINGER(src, len, mult)`

Enables:
- momentum indicators, z‑score mean reversion, Bollinger systems.

##### C) Domain‑specific quant tools (add later)
Add:
- `CORREL(src1, src2, len)`
- `COVAR(src1, src2, len)`
- `SLOPE(src, len)`
- `LINEAR_REG(src, len)`

Enables:
- beta‑like indicators, slope/trend metrics, statistical signals.

##### D) Multi‑timeframe tools (later)
Add:
- `HTF(src, "1d")` to project a lower‑TF series into higher‑TF resolution cleanly.

##### E) Multi‑symbol capabilities (later)
Add:
- `SPREAD(series1, series2)`
- `PAIR_RATIO(series1, series2)`
- `SECTOR_INDEX("NIFTY_IT")`

Enables:
- pair trading, sector/portfolio overlays, hedging indicators.

##### Mathematical extensions (as needed)
Add:
- `POW(x, y)`, `SQRT(x)`, `EXP(x)`, `LOG(x)`

The allowed function set must be declared and enforced at parse/compile time.

---

## 8) DSL (internal representation)

Even though most users won’t type DSL, the system stores a canonical DSL string for portability and evaluation.

### 8.1 DSL grammar (summary)

Logical:
```txt
EXPR    := OR_EXPR
OR_EXPR := AND_EXPR ('OR' AND_EXPR)*
AND_EXPR:= NOT_EXPR ('AND' NOT_EXPR)*
NOT_EXPR:= 'NOT' NOT_EXPR | PRIMARY
PRIMARY := REL_EXPR | EVENT_EXPR | '(' EXPR ')'
```

Relational:
```txt
REL_EXPR := ARITH_EXPR REL_OP ARITH_EXPR
REL_OP   := '<' | '>' | '<=' | '>=' | '==' | '!='
```

Arithmetic:
```txt
ARITH_EXPR := TERM (('+' | '-') TERM)*
TERM       := FACTOR (('*' | '/') FACTOR)*
FACTOR     := NUMBER | IDENT | FUNC_CALL | '(' ARITH_EXPR ')'
FUNC_CALL  := IDENT '(' ARG_LIST? ')'
ARG_LIST   := EXPR (',' EXPR)*
```

Events:
```txt
EVENT_EXPR := SERIES_EXPR EVENT_OP SERIES_EXPR_OR_CONST
EVENT_OP   := 'CROSSES_ABOVE' | 'CROSSES_BELOW' | 'MOVING_UP' | 'MOVING_DOWN'
SERIES_EXPR:= FUNC_CALL | IDENT | '(' SERIES_EXPR ')'
Note: for `MOVING_UP/DOWN`, RHS is numeric constant only (Phase 1).
```

### 8.2 Mapping UI → DSL

- Each condition row becomes `(LHS OP RHS)`
- Join mode becomes `AND`/`OR`
- Variables become identifiers
- Indicators become function calls
- Metrics become identifiers (reserved names)

Example:
```txt
(RSI_1H_14 < 30) AND (PRICE_1D > SMA_1D_200) AND (TODAY_PNL_PCT > 5)
```

---

## 9) Examples (end‑to‑end)

### Example 1 — Today PnL % over a group

Target: `Universe = t1`

Condition:
```txt
TODAY_PNL_PCT > 5
```

### Example 2 — Oversold RSI + long‑term support

Variables:
- `RSI_1H_14 = RSI(close, 14, "1h")`
- `SMA_1D_200 = SMA(close, 200, "1d")`
- `PRICE_1D = PRICE(close, "1d")`

Condition:
```txt
RSI_1H_14 < 30 AND PRICE_1D > SMA_1D_200
```

### Example 3 — MA crossover + volume spike

Variables:
- `SMA_1D_20 = SMA(close, 20, "1d")`
- `SMA_1D_50 = SMA(close, 50, "1d")`
- `VOL_1D = VOLUME("1d")`
- `VOL_1D_AVG = SMA(VOLUME("1d"), 20, "1d")`

Condition:
```txt
SMA_1D_20 CROSSES_ABOVE SMA_1D_50 AND VOL_1D > 2 * VOL_1D_AVG
```

---

## 10) Alert actions (Alert only / Buy / Sell) — Phase B

Goal: extend Alert V3 definitions so an alert can be either:
- **signal only** (`ALERT_ONLY`) — current behavior, no change, and
- **signal + execution intent** (`BUY` / `SELL`) — store a symbol‑free buy/sell template that can be applied to each per‑symbol trigger.

### 10.1 UX requirement

In the alert editor:
- Add `Action` selector: `Alert only` / `Buy` / `Sell` (default = `Alert only`).
- When `Buy` or `Sell` is selected, show an additional tab: `Buy template` / `Sell template`.
- Template tab: mirror the Holdings buy/sell dialog, except it excludes symbol-specific UI and the `% of portfolio` sizing option.

### 10.2 Data model (backwards compatible)

Add fields to the persisted alert definition:
- `action_type`: `ALERT_ONLY` | `BUY` | `SELL`
- `action_params`: JSON (template payload)

Notes:
- Existing alerts default to `ALERT_ONLY` automatically (no behavior change).
- `action_params` is ignored when `action_type = ALERT_ONLY`.
- The server should canonicalize `action_params` so `mode` and `execution_target` are always present for `BUY`/`SELL` (with safe defaults).

Example create payload (MVP):

```json
{
  "name": "RSI oversold (buy holdings)",
  "target_kind": "HOLDINGS",
  "target_ref": "ZERODHA",
  "action_type": "BUY",
  "action_params": { "mode": "MANUAL", "execution_target": "LIVE" },
  "variables": [{ "name": "RSI_1H_14", "dsl": "RSI(close, 14, \"1h\")" }],
  "condition_dsl": "RSI_1H_14 < 30",
  "trigger_mode": "ONCE_PER_BAR",
  "enabled": true
}
```

### 10.3 Runtime semantics (high-level)

Independently of action type:
- Every trigger still creates an `AlertEvent` record (audit/debugging stays intact).

When `action_type` is `BUY` or `SELL`:
- Each per‑symbol trigger should produce an **OrderIntent** derived from the template + the triggered symbol.
- Routing uses the same mental model as the holdings buy/sell dialog:
  - `MANUAL` → goes to the waiting queue
  - `AUTO` → goes directly to execution (or into an auto queue) depending on how AUTO is implemented today
  - `PAPER` → executes against the paper engine (no broker contact)

Important: this section is intentionally **high-level**. Worker orchestration and broker routing remain documented elsewhere; this document focuses on contract + semantics.

### 10.4 Key challenges / guardrails

These must be explicitly handled before enabling AUTO+LIVE in production:
- **Idempotency / de-duplication**: guard against repeated triggers creating duplicate orders (dedupe key like `(alert_id, symbol, bar_time, action_type)`).
- **Position awareness** (later): “buy” for already-held symbols, “sell” for non-held symbols — should be a template option (skip vs error vs allow short).
- **Auditability**: store the resolved template (including defaults) alongside the created intent/order so users can inspect “what got sent”.
- **Security**: only accept execution parameters from persisted alert definitions (never from external webhook payloads).

---

## 11) Migration notes (from current system)

We already have working building blocks:
- Universe targeting (holdings + groups)
- A DSL / expression engine foundation
- Indicator computations
- Holdings metrics fields (e.g. `TODAY_PNL_PCT`)

Refactor direction:

1) Align UI terminology:
   - Alerts are conditions + target; remove “strategy” naming from alert creation.
2) Implement the wizard:
   - Target → Variables → Conditions → Trigger settings → Save.
3) Add Indicators tab:
   - show built‑ins + custom indicators with guardrails.
4) Add Events tab:
   - show trigger history + snapshots for trust/debugging.

### 11.1 Phase 1 cutover: remove legacy indicator-rule alerts

This repo now treats **Alert V3** as the default/primary alerts system.

What changed (Phase 1):
- **Holdings per‑symbol “ALERT” button** now opens the Alert V3 create dialog pre‑filled as:
  - `target_kind = SYMBOL`
  - `target_ref = <clicked symbol>`
  - `exchange = <symbol exchange>`
  This is implemented as a simple deep‑link into `/alerts` with query params, so we reuse the same create UI.
- The **Alerts page no longer shows the Legacy tab** in the UI (V3 only: Alerts / Indicators / Events).
- Legacy indicator‑rule alert backend plumbing is **guarded** behind `ST_ENABLE_LEGACY_ALERTS` (default `0`):
  - When disabled: legacy routes aren’t mounted and the legacy scheduler isn’t started.
  - Under pytest: legacy is force‑enabled so existing tests can still run during the migration window.
- Legacy definitions are **purged from DB** via Alembic migration `0028_purge_legacy_indicator_rules.py`:
  - Preserves `alerts` history rows but nulls `alerts.rule_id` before deleting from `indicator_rules`.

Why this is safe:
- V3 alerts already cover both “single symbol” and “universe” use‑cases, so per‑symbol legacy alerts are redundant.
- Keeping the legacy code path behind a flag provides a short safety window for rollback of runtime behavior (but legacy rule *definitions* are intentionally deleted).

What remains (Phase 2+):
- Re‑implement **Screener** on top of Alert V3.
- Once Screener no longer depends on the legacy DSL/indicator alert machinery, delete the remaining legacy code paths entirely.

---

## 12) Open decisions (confirm before implementation)

1) Selected rows:
   - Confirmed: strongly guide “Create group from selection”.
2) MOVING_UP/DOWN RHS:
   - Confirmed: numeric only.
3) Evaluation cadence:
   - Confirmed: per‑alert cadence (default to smallest referenced timeframe, overridable).
4) Custom indicator function surface:
   - Confirmed: start with MVP surface (A) and expand intentionally through B→E.

5) Action template (Phase B):
   - Confirm which template fields are required before we allow `AUTO + LIVE` (sizing, order_type/product, bracket/GTT, position guards, risk gating).
