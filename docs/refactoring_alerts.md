# Alerts Refactoring — Indicator‑First, Universe‑Scoped (Reference)

## 1) Goal

Redesign alerts so they are simple, TradingView‑like, and bulk‑friendly, with a clear mental model:

- An **Alert** monitors either:
  - a **single symbol**, or
  - a **universe** (a group), where universe can be:
    - **Holdings (Zerodha)**, or
    - a named group such as `t1`, `famous5`, etc.
- Alerts contain **only conditionals** (rules). The engine evaluates the condition **per symbol** inside the target universe.
- Indicators are **decoupled** from alerts:
  - an **Indicators** area lists built‑in indicators, supports custom indicators, and controls which indicators are available for use.

This document is a reference design (concepts, UX wireframes, language, and migration notes).

---

## 2) The core model (what loops where)

Your key observation is correct: “many alerts per symbol” vs “one alert over many symbols” is mostly about where the loop lives.

### 2.1 The model

An alert is the “actor”, and the system loops symbols inside the alert engine:

```
for each alert A:
  symbols = resolve(A.target)   // symbol or universe
  for each symbol S in symbols:
    if evaluate(A.condition, S) is true:
      emit AlertEvent(A, S, snapshot)
```

This naturally supports:
- multiple alerts on a symbol (many actors),
- a single alert covering many symbols (one actor),
- bulk/universe usage without duplicating per‑symbol rules.

---

## 3) Vocabulary & entities

### 3.1 Universe (group)

Universe = a set of symbols:
- `Holdings (Zerodha)` — dynamic membership (changes with holdings)
- `Group: t1 / famous5 / …` — dynamic membership (changes with group members)

### 3.2 Alert

An Alert is a persisted object with:
- `name`
- `target`: either
  - `SYMBOL(symbol, exchange?)`, or
  - `UNIVERSE(kind, id)` where kind is `HOLDINGS` or `GROUP`
- `condition`: boolean expression (see section 5)
- `trigger_mode` (optional; see section 6)
- `time_constraints` (optional):
  - enabled/disabled
  - optional expiry date/time
  - optional market‑hours gating

### 3.3 Indicator (decoupled)

Indicator = a reusable computation definition. Alerts reference indicators via variables.

Indicators live in an Indicators catalog:
- built‑in indicators (RSI, SMA, EMA, VWAP, ATR, …)
- primitives (OHLCV fields)
- custom indicators (user‑defined; composed from built‑ins)
- enable/disable indicator availability in the UI

This catalog is separate from alerts.

### 3.4 AlertEvent (history)

AlertEvent is an immutable record created when an alert triggers for a symbol.

Minimum fields:
- `alert_id`, `alert_name`
- `symbol`, `exchange`
- `triggered_at`
- `reason` (serialized condition summary)
- `snapshot` (values of variables used in evaluation)

This is crucial for trust/debugging (“why did this fire?”).

---

## 4) UX design (wireframes)

### 4.1 Navigation

```
Alerts
------------------------------------------------
Tabs:  [ Alerts ]  [ Indicators ]  [ Events ]
```

- Alerts: create/edit/enable/disable alerts; show scope and condition summary.
- Indicators: browse built‑ins, define custom indicators, enable/disable.
- Events: trigger history with filters by alert/symbol/universe/timeframe.

### 4.2 Create Alert (wizard, TradingView‑like)

The wizard optimizes for: “I want an alert if X happens in universe Y”.

#### Step 1 — Target

```
Create Alert
------------------------------------------------
Target:
( ) Symbol      [ AARTIPHARM ] [ NSE ]
( ) Universe    [ Holdings (Zerodha) | t1 | famous5 | ... ]

Preview: Universe has N symbols

[ Next ]
```

Notes:
- Universe is the first‑class bulk mechanism.
- “Selected rows” (optional) should be modeled as:
  - “Temporary universe (static list)”, or
  - “Create a group from selection”.

#### Step 2 — Variables (optional but powerful)

Variables make complex rules readable and re‑usable inside the alert.

```
Variables (optional)
------------------------------------------------
Define reusable variables to use in conditions.

Name                  Indicator  OHLCV  Bars  TF
-------------------------------------------------
RSI__close_14_1h       RSI        C      14    1h
SMA__close_50_1d       SMA        C      50    1d

[ + Add variable ]  [ Next ]
```

Design notes:
- Variables are local to an alert by default (Phase 1).
- Later we can let users save variables as indicator templates in the Indicators tab.

#### Step 3 — Condition (screener‑like)

Condition builder mirrors the screener mental model:
- compare indicator/column to value OR indicator/column
- combine with AND / OR
- support crossing/moving operators

```
Condition Builder
------------------------------------------------
Match:  ( ) All conditions (AND)   ( ) Any (OR)

[ LHS ]                [ OP ]               [ RHS ]
----------------------------------------------------------
SMA__close_50_1d        >                   500
RSI__close_14_1h        <                   30

[ + Add condition ]

Expression preview:
(SMA__close_50_1d > 500) AND (RSI__close_14_1h < 30)

[ Next ]
```

#### Step 4 — Trigger behavior (how often)

```
Trigger Settings
------------------------------------------------
Trigger mode:
( ) ONCE                // fire once per symbol
( ) ONCE_PER_BAR        // fire at most once per bar per symbol
( ) EVERY_TIME          // fire whenever true (use throttle)

Throttle (optional):
At most once per symbol per [ 30 ] minutes

Expiry (optional):
Stop after [ date/time ]

[ Create Alert ]
```

### 4.3 Bulk Alert entry points in Universe grids

You can add a “Bulk Alert” button next to Bulk Buy/Sell, but its job is only to open the Create Alert wizard with the target pre‑selected:

- If you are in a group universe: default target = that universe (dynamic).
- If you are in holdings and have selected rows:
  - default target = “Temporary universe from selected rows” with one‑click “Save as group”.

This keeps “alert = actor over a set”, not “per‑row alerts”.

---

## 5) The Alert language (conditions, variables, comparisons)

You want alerts to be “like screener”, but more powerful (TradingView‑like). That implies:

### 5.1 Operands (what can be compared)

An operand can be:

1) Value: number (e.g. `5`, `-2.5`, `500`)
2) Variable: a named computed value, e.g. `RSI__close_14_1h`
3) Column/Metric: holdings/universe metrics such as `TODAY_PNL_PCT`, `PNL_PCT`, etc.

Comparisons can be:
- operand OP value
- operand OP operand

### 5.2 Operators (within a condition)

You specified these operators:

- comparisons: `<, <=, >, >=, ==, !=`
- cross: `CROSSING_ABOVE`, `CROSSING_BELOW`
- move: `MOVING_UP`, `MOVING_DOWN`

We should define exact semantics so results are predictable and trusted.

#### 5.2.1 CROSSING_ABOVE / CROSSING_BELOW

Evaluated using current and previous values:

- `A CROSSING_ABOVE B` is true when:
  - `A_prev <= B_prev` AND `A_now > B_now`
- `A CROSSING_BELOW B` is true when:
  - `A_prev >= B_prev` AND `A_now < B_now`

If RHS is a constant number, treat `B_prev == B_now == constant`.

#### 5.2.2 MOVING_UP / MOVING_DOWN

We need one consistent meaning. Recommended default: percent change over the last bar:

- `A MOVING_UP x` means: `((A_now - A_prev) / abs(A_prev)) * 100 >= x`
- `A MOVING_DOWN x` means: `((A_prev - A_now) / abs(A_prev)) * 100 >= x`

If you want absolute move as well, expose both explicitly:
- `MOVING_UP_PCT`, `MOVING_DOWN_PCT` (percent)
- `MOVING_UP_ABS`, `MOVING_DOWN_ABS` (absolute)

### 5.3 Variable definition model

You want to define variables like:

```
<name> <indicator> <OHLVC_value> <bars> <timeframe>
RSI__close_14_1h RSI C 14 1h
```

Define variable schema as:

- `name`: string (unique within the alert)
- `indicator`: kind (RSI/SMA/EMA/VWAP/ATR/PERF/etc)
- `ohlcv`: one of `O, H, L, C, V`
- `bars`: integer parameter (lookback)
- `timeframe`: `1m`, `5m`, `1h`, `1d`, ...

Examples:
- `RSI__close_14_1h` → `RSI(ohlcv=C, bars=14, timeframe=1h)`
- `SMA__close_50_1d` → `SMA(ohlcv=C, bars=50, timeframe=1d)`

### 5.4 Expression composition

Expressions combine comparisons via `AND` / `OR`. Parentheses should be supported eventually; UI can start with a flat list + AND/OR toggle.

Example:
```
SMA__close_50_1d > 500 AND RSI__close_14_1h < 30
```

### 5.5 Compare column/indicator to column/indicator

Supported naturally:
```
PRICE__close_1d > SMA__close_50_1d
TODAY_PNL_PCT > PNL_PCT
RSI__close_14_1h CROSSING_ABOVE 50
```

---

## 6) Scheduling, timeframe, and evaluation

### 6.1 Timeframe source of truth

An alert can have variables with different timeframes; this is a feature, not a bug.

Example in one alert:
- `RSI(close, 14, 1h)` AND `SMA(close, 50, 1d)`

### 6.2 Missing data behavior

Safe default:
- if an operand can’t be computed → condition evaluates to false for that symbol.

Events/debug should show missing‑data reasons (optional).

### 6.3 Trigger modes and throttling

Trigger modes reduce noise:
- ONCE (per symbol)
- ONCE_PER_BAR
- EVERY_TIME (requires throttle)

Throttle is TradingView‑style “don’t spam”.

---

## 7) Indicators system (decoupled, but practical)

To keep the design lean, don’t overbuild the catalog immediately.

### Phase 1 — Built‑ins + alert‑local variables
- Show built‑in indicators and primitives (OHLCV).
- Allow defining variables inside an alert.
- Allow enabling/disabling indicator kinds available in UI.

### Phase 2 — Custom indicators (reusable)
- Let users define named custom indicators as compositions of built‑ins.
- Version them so alerts can remain stable or opt‑in to updates.

---

## 8) Migration from current system (keep what works, remove flab)

We already have useful building blocks:
- universe targeting (holdings + groups)
- field metrics (e.g., `TODAY_PNL_PCT`)
- indicator computations
- expression parsing infrastructure (DSL)

Migration approach:

1) UI: keep the “Create alert rule” entry points, but refocus on:
   - Target → Variables → Conditions → Trigger settings
2) Conceptual rename:
   - remove “strategy” terminology from alert UX.
3) If/when trading automation is desired:
   - make it a separate consumer of AlertEvents, or a separate “Automation” layer.

---

## 9) Decisions needed to finalize

1) Confirm “alerts only conditionals” means:
   - alerts emit events/logs/notifications, and trading is handled separately.
2) Confirm moving semantics:
   - percent vs absolute (recommend percent as default).
3) Selected rows handling:
   - allow temporary static universe vs force “create group first”.

---

## 10) Example (end‑to‑end)

Goal: “In group `t1`, fire when 1h RSI is oversold and 1d SMA is strong”.

Target:
- Universe = `t1` (dynamic)

Variables:
- `RSI__close_14_1h = RSI(C, 14, 1h)`
- `SMA__close_50_1d = SMA(C, 50, 1d)`

Condition:
```
SMA__close_50_1d > 500 AND RSI__close_14_1h < 30
```

Trigger:
- ONCE_PER_BAR + throttle 30m

Result:
- One alert monitors the universe; evaluation is per symbol; events are stored per symbol.
