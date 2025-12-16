Here’s a fresh design doc that builds on your existing refactor notes and folds in the richer DSL / custom-indicator ideas so you can realize *complex alerts via UI* (without exposing raw code).



---

# Alert Creation UX & DSL Design v1

## 1. Purpose & Scope

This document defines **how users create alerts through the UI** in SigmaTrader using:

* **Indicators & OHLCV fields** (built-in)
* **Custom indicators** (user-defined)
* A **safe alert DSL** under the hood

Goals:

* TradingView-like ease-of-use, but with **richer logic** (crossovers, multi-TF, custom scores).
* Alerts work over **single symbols or universes**.
* UI users never need to see DSL syntax, but the system stores alerts as **DSL expressions** for evaluation and portability.

This document focuses only on **creating & editing alerts** (UX + expression model). The runtime evaluation engine, events, etc. follow your existing refactor design. 

---

## 2. Core Concepts (Alert, Universe, Indicator, Expression)

We adopt the same conceptual model as your refactor:

### 2.1 Universe

A **Universe** is a set of symbols:

* `Holdings (Zerodha)` – dynamic, based on broker positions
* `Group: t1, famous5, …` – user-defined lists
* Later: `Watchlist: <name>`, `Index: NIFTY50`, etc.

### 2.2 Alert

An **Alert** is a persisted object:

* `name`
* `target` – `SYMBOL(x)` or `UNIVERSE(kind, id)`
* `condition` – boolean DSL expression (per symbol)
* `trigger_mode` – ONCE / ONCE_PER_BAR / EVERY_TIME (+ throttle)
* `time_constraints` – market hours / expiry

The engine loops symbols **inside** each alert:

```pseudo
for each Alert A:
  symbols = resolve(A.target)
  for each symbol S in symbols:
    if evaluate(A.condition, S) == true:
      emit AlertEvent(A, S, snapshot)
```

### 2.3 Indicator

An **Indicator** is a reusable computation:

* Built-in (RSI, SMA, EMA, ATR, VWAP, etc.)
* Primitives (OHLCV: open, high, low, close, volume)
* Custom (composed indicators defined by the user)

### 2.4 Expression / Condition

* A **Condition** is a boolean expression built from:

  * indicators, OHLCV fields, constants
  * operators (`<, >, <=, >=, ==, !=, CROSSES_ABOVE, CROSSES_BELOW, MOVING_UP, MOVING_DOWN`)
  * logical connectives (`AND`, `OR`, optional `NOT` later)
* Alerts are basically:
  **“For each symbol in this target, if this expression is true, trigger.”**

---

## 3. High-Level UI Layout

Top-level navigation:

```
Alerts
------------------------------------------------
Tabs: [ Alerts ]  [ Indicators ]  [ Events ]
```

* **Alerts tab** → list, create, edit, enable/disable alerts.
* **Indicators tab** → manage built-ins visibility, define custom indicators.
* **Events tab** → history of triggered alerts (debug / audit).

This doc focuses on:

* **Create / Edit Alert** flow (Alerts tab)
* **Create / Edit Custom Indicator** flow (Indicators tab)

---

## 4. Alert Creation Flow (Wizard)

### 4.1 Step 1 — Target & Meta

**Goal:** specify where this alert runs and basic metadata.

UI:

* **Name**: free-text input.
* **Target type**:

  * `( ) Single Symbol` – [ Symbol dropdown ] [ Exchange dropdown ]
  * `( ) Universe` – [ Holdings (Zerodha) | Group: t1 | Group: famous5 | … ]
* **Preview**:

  * “Universe `t1` currently has **23 symbols**”
  * “Symbol `INFY` (NSE)”

Optional:

* Market hours gating: checkbox “Only during market hours”
* Optional expiry date/time

**Resulting model:**

```json
{
  "name": "1h RSI Oversold on Holdings",
  "target": {
    "type": "UNIVERSE",
    "kind": "HOLDINGS",
    "id": "ZERODHA"
  },
  "time_constraints": { ... }
}
```

---

### 4.2 Step 2 — Variables (Local Indicator Variables)

**Goal:** give friendly **names** to indicator computations to make conditions simple and readable.

UI: a small grid:

| Name        | Type  | Source | Length | Timeframe | Advanced… |
| ----------- | ----- | ------ | ------ | --------- | --------- |
| `RSI_1H_14` | RSI   | Close  | 14     | 1h        | (…)       |
| `SMA_1D_50` | SMA   | Close  | 50     | 1d        | (…)       |
| `PRICE_1D`  | Price | Close  | 1      | 1d        | (…)       |

* **Type**: dropdown: RSI, SMA, EMA, ATR, VWAP, PRICE, VOLUME, CUSTOM_INDICATOR…
* **Source**: OHLCV field (Open, High, Low, Close, Volume).
* **Length**: integer lookback (for most indicators).
* **Timeframe**: dropdown (1m, 5m, 15m, 1h, 1d, etc.).
* **Custom indicator**: if selected, show custom indicator list and its parameters.

Examples:

* `RSI_1H_14` → `RSI(close, 14, "1h")`
* `SMA_1D_50` → `SMA(close, 50, "1d")`
* `SWING_SCORE_1D` (custom) → `SWING_SCORE_1D(close)` (defined under Indicators tab)

Variables are **local** to this alert (Phase 1). In the future, we can add “Save as shared alias”.

**Data model for variable:**

```json
{
  "name": "RSI_1H_14",
  "kind": "RSI",
  "params": {
    "source": "close",
    "length": 14,
    "timeframe": "1h"
  }
}
```

Backend uses this when building/evaluating the DSL expression.

---

### 4.3 Step 3 — Condition Builder (Expression UI)

**Goal:** build complex boolean expressions using variables, built-in fields, and constants—without exposing DSL syntax.

Conceptually we’re building a DSL expression of the form:

```txt
EXPR := OR_EXPR
OR_EXPR := AND_EXPR ('OR' AND_EXPR)*
AND_EXPR := NOT_EXPR ('AND' NOT_EXPR)*
NOT_EXPR := 'NOT' NOT_EXPR | PRIMARY
PRIMARY := REL_EXPR | EVENT_EXPR | '(' EXPR ')'
```

But we present it visually.

#### 4.3.1 Simple “Row” Mode (Phase 1)

UI:

* A table of **conditions**, each row:

| Join | LHS Operand | Operator        | RHS Operand |
| ---- | ----------- | --------------- | ----------- |
|      | `RSI_1H_14` | `<`             | `30`        |
| AND  | `PRICE_1D`  | `<`             | `SMA_1D_50` |
| AND  | `RSI_1H_14` | `CROSSES_ABOVE` | `30`        |

* **Join** column: AND / OR (first row has none).
* **Operand picker** (for LHS & RHS) allows:

  * Variable: any variable from step 2
  * Column: e.g., `PNL_PCT`, `TODAY_PNL_PCT`, `POSITION_SIZE`, etc.
  * Constant: numeric, %, bool (e.g., 30, `2.5%`, `TRUE`)
* **Operator** dropdown:

  * For numeric comparisons: `<, >, <=, >=, ==, !=`
  * For series events:

    * `CROSSES_ABOVE`
    * `CROSSES_BELOW`
    * `MOVING_UP`
    * `MOVING_DOWN`

Under the hood, this maps to:

* Numeric comparison: `ARITH_EXPR REL_OP ARITH_EXPR`
* Event: `SERIES_EXPR EVENT_OP SERIES_EXPR`

Example built from UI rows:

```txt
(RSI_1H_14 < 30)
AND (PRICE_1D < SMA_1D_50)
AND (RSI_1H_14 CROSSES_ABOVE 30)
```

We also show a **read-only expression preview** field:

```txt
Expression preview:
(RSI_1H_14 < 30) AND (PRICE_1D < SMA_1D_50) AND (RSI_1H_14 CROSSES_ABOVE 30)
```

This is the actual DSL string saved with the alert.

#### 4.3.2 Advanced Mode: Parentheses

Later, enable an “Advanced mode” toggle:

* Users can explicitly group conditions:

  * For example: `(A AND B) OR (C AND D)`
* UI: a small tree/indent UI or “group” rows into blocks.

Advanced expression preview is still maintained by the backend.

---

### 4.4 Step 4 — Trigger Settings

Same as your refactor, but framed as the final step.

UI:

* **Trigger mode** (per symbol):

  * `( ) ONCE` – first time condition turns true for that symbol, never again
  * `( ) ONCE_PER_BAR` – at most once per bar (per timeframe basis)
  * `( ) EVERY_TIME` – every evaluation where condition is true

* **Throttle** (when EVERY_TIME is chosen):

  * “At most once per symbol every [ 15 ] minutes”

* **Expiry** (optional):

  * “Stop this alert on [ date + time ]”

---

### 4.5 Step 5 — Review & Save

Show a compact review:

* Name
* Target (with preview symbol count)
* Variable summary
* Condition preview (DSL string)
* Trigger/expiry

Buttons:

* [Back] / [Save Alert]

Optional:

* “Test on last bar” – evaluate the condition for a couple of symbols in the target universe and display:

  * `INFY: FALSE (RSI_1H_14=42.3, SMA_1D_50=1535.2, PRICE_1D=1510.9)`
  * `TCS: TRUE (RSI_1H_14=28.1, SMA_1D_50=3720.5, PRICE_1D=3660.0)`

This builds trust.

---

## 5. Custom Indicators: UX & Design

Custom indicators are more powerful “indicator functions” that users can plug into alerts as if they were primitives.

### 5.1 Concept

A **Custom Indicator**:

* Has a name (ID)
* Has parameters (optionally)
* Is defined as an **expression** of other indicators & OHLCV fields
* Returns a numeric value per bar per symbol

Examples:

* `SWING_SCORE_1D(src)`
* `VALUE_SCORE(src)`
* `VOLATILITY_INDEX(src, length)`

### 5.2 Indicators Tab UI

`Indicators` tab layout:

* **Built-in indicators** list (read-only info + enable/disable in UI).

* **Custom indicators** section with:

  | Name             | Params | Timeframes | Enabled |
  | ---------------- | ------ | ---------- | ------- |
  | `SWING_SCORE_1D` | `src`  | 1d         | ✅       |
  | `VALUE_SCORE`    | `src`  | 1d         | ✅       |

* [Create Custom Indicator] button.

### 5.3 Custom Indicator Creation Flow

1. **Definition metadata**

   * Name: `SWING_SCORE_1D`
   * Description: “Measures swinginess based on ATR% and volatility”
   * Parameters: typed list:

     * `src: price_series`
     * `len_atr: int = 14` (default)
     * `len_vol: int = 20` (optional)

2. **Formula / Expression Builder**

   Reuse the **arithmetic expression builder**:

   * Operands: built-in indicator funcs, OHLCV fields, constants, other custom indicators.
   * Operators: `+ - * /`, parentheses.

   Example formula (visually built):

   ```txt
   SWING_SCORE_1D(src) =
       ( ATR(src, len_atr, "1d") / PRICE("1d") * 100 )
     + ( StdDev(returns(src, "1d"), len_vol) * 100 )
   ```

   The underlying DSL grammar:

   ```txt
   ARITH_EXPR := TERM (('+' | '-') TERM)*
   TERM       := FACTOR (('*' | '/') FACTOR)*
   FACTOR     := NUMBER | IDENT | FUNC_CALL | '(' ARITH_EXPR ')'
   ```

3. **Validation**

   * Check for recursion (indicator calling itself).
   * Check param usage (all parameters referenced, no unknown ones).
   * Check type compatibility (series vs scalar where relevant).

4. **Save & Enable**

   Once saved, this indicator appears in:

   * Variables step (Type = Custom → choose `SWING_SCORE_1D`).
   * Condition builder operand picker (via variable names).

Backend stores custom indicator as something like:

```json
{
  "name": "SWING_SCORE_1D",
  "params": ["src", "len_atr", "len_vol"],
  "body": "ATR(src, len_atr, \"1d\") / PRICE(\"1d\") * 100 + StdDev(returns(src, \"1d\"), len_vol) * 100"
}
```

---

## 6. Alert DSL (Internal Representation)

Although the user never types it, every alert has a **canonical DSL string** representing `condition`.

### 6.1 Expression Grammar (summary)

* **Logical:**

  ```txt
  EXPR    := OR_EXPR
  OR_EXPR := AND_EXPR ('OR' AND_EXPR)*
  AND_EXPR:= NOT_EXPR ('AND' NOT_EXPR)*
  NOT_EXPR:= 'NOT' NOT_EXPR | PRIMARY
  PRIMARY := REL_EXPR | EVENT_EXPR | '(' EXPR ')'
  ```

* **Relational:**

  ```txt
  REL_EXPR := ARITH_EXPR REL_OP ARITH_EXPR
  REL_OP   := '<' | '>' | '<=' | '>=' | '==' | '!='
  ```

* **Arithmetic:**

  ```txt
  ARITH_EXPR := TERM (('+' | '-') TERM)*
  TERM       := FACTOR (('*' | '/') FACTOR)*
  FACTOR     := NUMBER | IDENT | FUNC_CALL | '(' ARITH_EXPR ')'
  FUNC_CALL  := IDENT '(' ARG_LIST? ')'
  ARG_LIST   := EXPR (',' EXPR)*
  ```

* **Events (crossings/moves):**

  ```txt
  EVENT_EXPR := SERIES_EXPR EVENT_OP SERIES_EXPR
  EVENT_OP   := 'CROSSES_ABOVE' | 'CROSSES_BELOW' | 'MOVING_UP' | 'MOVING_DOWN'
  SERIES_EXPR:= FUNC_CALL | IDENT | '(' SERIES_EXPR ')'
  ```

Indicators and variables map to `IDENT` or `FUNC_CALL`, and the UI ensures the DSL is always valid.

---

## 7. Implementation Notes & Guardrails

### 7.1 Evaluation Semantics for Events

* `A CROSSES_ABOVE B`:

  * `A_prev <= B_prev AND A_now > B_now`
* `A CROSSES_BELOW B`:

  * `A_prev >= B_prev AND A_now < B_now`
* `A MOVING_UP x`:

  * `((A_now - A_prev) / |A_prev|) * 100 >= x`
* `A MOVING_DOWN x`:

  * `((A_prev - A_now) / |A_prev|) * 100 >= x`

### 7.2 Multi-Timeframe Handling

Variables may use different timeframes in one alert. Engine must:

* Fetch/compute all needed timeframes per symbol.
* Align latest completed candles (don’t use partially formed bar unless explicitly allowed).

When data is missing:

* Safest default: condition = **false** for that symbol on that evaluation.
* Optionally log “missing data” diagnostics for debugging.

### 7.3 Safety

* The user never runs arbitrary code; all they do is compose from:

  * Pre-vetted indicators
  * Custom indicators defined via controlled arithmetic expressions
* Evaluation is pure & deterministic, easy to test.

---

## 8. Examples (End-to-End)

### Example 1: Oversold RSI with Long-Term Support

**Variables:**

* `RSI_1H_14` = `RSI(close, 14, "1h")`
* `SMA_1D_200` = `SMA(close, 200, "1d")`
* `PRICE_1D`   = `PRICE("1d")`

**Condition rows:**

1. `RSI_1H_14` `<` `30`
2. AND `PRICE_1D` `>` `SMA_1D_200`

DSL:

```txt
RSI_1H_14 < 30 AND PRICE_1D > SMA_1D_200
```

---

### Example 2: Trend Reversal — MA Crossover with Volume Spike

Variables:

* `SMA_1D_20`  = `SMA(close, 20, "1d")`
* `SMA_1D_50`  = `SMA(close, 50, "1d")`
* `VOL_1D`     = `VOLUME("1d")`
* `VOL_1D_AVG` = `SMA(VOLUME("1d"), 20, "1d")`

Condition:

1. `SMA_1D_20` `CROSSES_ABOVE` `SMA_1D_50`
2. AND `VOL_1D` `>` `2 * VOL_1D_AVG`

DSL:

```txt
SMA_1D_20 CROSSES_ABOVE SMA_1D_50 AND VOL_1D > 2 * VOL_1D_AVG
```

---

### Example 3: Using a Custom Indicator `SWING_SCORE_1D`

Custom indicator defined in Indicators tab:

```txt
SWING_SCORE_1D(src) =
    ATR(src, 14, "1d") / PRICE("1d") * 100
  + StdDev(returns(src, "1d"), 20) * 100
```

Alert variables:

* `SWING` = `SWING_SCORE_1D(close)`
* `RSI_1D_14` = `RSI(close, 14, "1d")`

Condition:

1. `SWING` `>` `8`
2. AND `RSI_1D_14` BETWEEN `40` AND `60` (optional DSL extension)

DSL:

```txt
SWING > 8 AND RSI_1D_14 >= 40 AND RSI_1D_14 <= 60
```

---

## 9. Summary

This design gives you:

* A **clean, indicator-first alert model** that works over universes.
* A **UI-friendly condition builder** that maps cleanly to a robust DSL.
* **Custom indicator support** via controlled expressions, not arbitrary code.
* Clear semantics for **events** (crosses, moving up/down).
* A path to add more complexity (parentheses, NOT, fundamentals, Monte Carlo signals) without breaking the mental model.

If you’d like, next step I can:

* Turn this into **actual UI component wireframes** (for your existing frontend stack),
* Or design the **Python/Node backend API contracts** for alerts, indicators, and evaluation.  

---

Below is a **clean, detailed, professional wireframe** set for your **Alerts Module** — designed to fit your SigmaTrader UI style.
I am giving **ASCII wireframes** (UI layout sketches) that you can directly translate into React/Vue/Svelte or your existing frontend framework.

If you want **Figma-style graphic wireframes**, I can also generate them using an image-group — just say the word.

---

# 🟦 **1. Alerts List Page (Home)**

Purpose: show all alerts, enable/disable, quick status, edit/delete.

```
+---------------------------------------------------------------+
|  ALERTS                                                       |
+---------------------------------------------------------------+
| [ + CREATE ALERT ]                                            |
+---------------------------------------------------------------+
|                                                               |
|  +---------------------------------------------------------+  |
|  | Name: RSI Oversold 1H on Holdings                      |  |
|  | Target: Universe: Holdings (Zerodha)                   |  |
|  | Condition: (RSI_1H_14 < 30 AND PRICE_1D < SMA_1D_50)   |  |
|  | Status:  ● Enabled     Last Trigger: 2025-01-15 10:32  |  |
|  | [ Edit ] [ Disable ] [ Delete ]                        |  |
|  +---------------------------------------------------------+  |
|                                                               |
|  +---------------------------------------------------------+  |
|  | Name: Breakout with Volume Spike                         |  |
|  | Target: Symbol: INFY                                      |  |
|  | Condition: SMA_20 CROSSES_ABOVE SMA_50 AND VOL > 2*AVG  |  |
|  | Status:  ○ Disabled    Last Trigger: None               |  |
|  | [ Edit ] [ Enable ] [ Delete ]                          |  |
|  +---------------------------------------------------------+  |
|                                                               |
+---------------------------------------------------------------+
```

Features:

* Enable/Disable toggle
* “Last Trigger” timestamp
* Compact condition preview
* Link to edit

---

# 🟦 **2. Create Alert — Step 1: Meta & Target**

```
+---------------------------------------------------------------+
|  CREATE ALERT  (1/4)                                          |
+---------------------------------------------------------------+
| Alert Name:  [____________________________________________]   |
|                                                               |
| Target Type:                                                  |
|   (•) Universe                                                |
|        Universe: [Holdings (Zerodha)  v]                      |
|        Preview: 23 symbols                                    |
|   ( ) Single Symbol                                           |
|        Symbol: [INFY v]   Exchange: [NSE v]                   |
|                                                               |
| Options:                                                      |
|   [ ] Only evaluate during market hours                       |
|   [ ] Alert expires on:  [ 2025-03-01   15:30 ]               |
|                                                               |
|                    [ Next → ]                                 |
+---------------------------------------------------------------+
```

---

# 🟦 **3. Create Alert — Step 2: Define Variables (Indicators)**

Variables make complex conditions easy to build.

```
+---------------------------------------------------------------+
|  CREATE ALERT  (2/4)  —  Variables                            |
+---------------------------------------------------------------+
|  Variables define reusable indicator values for the alert.    |
|  Example:  RSI_1H_14 = RSI(close, 14, 1h)                     |
+---------------------------------------------------------------+
|  [ + Add Variable ]                                           |
+---------------------------------------------------------------+
|  Name          | Indicator Type | Source | Len | Timeframe | X |
|----------------------------------------------------------------|
|  RSI_1H_14     | RSI            | close  | 14  | 1h        | ✕ |
|  SMA_1D_50     | SMA            | close  | 50  | 1d        | ✕ |
|  PRICE_1D      | PRICE          | close  | –   | 1d        | ✕ |
+---------------------------------------------------------------+
|                    [ Back ]   [ Next → ]                      |
+---------------------------------------------------------------+
```

Future: Add variable presets + custom indicators.

---

# 🟦 **4. Create Alert — Step 3: Condition Builder (Expression)**

This is the core of alert creation.

```
+---------------------------------------------------------------+
|  CREATE ALERT  (3/4)  —  Condition                            |
+---------------------------------------------------------------+
|  Build your condition:                                       |
|  Alert fires when the condition evaluates TRUE for a symbol. |
+---------------------------------------------------------------+
|  [ + Add Condition Row ]                                      |
+---------------------------------------------------------------+
| Join |        Left Operand      |    Operator     | Right Op |
|----------------------------------------------------------------|
|      | [RSI_1H_14       ▼]       | [ < ▼ ]         | [ 30    ] |
| AND  | [PRICE_1D        ▼]       | [ < ▼ ]         | [SMA_1D_50▼] |
| AND  | [RSI_1H_14       ▼]       | [CROSSES_ABOVE▼]| [ 30    ] |
+---------------------------------------------------------------+
| Expression Preview:                                           |
| (RSI_1H_14 < 30) AND (PRICE_1D < SMA_1D_50)                   |
| AND (RSI_1H_14 CROSSES_ABOVE 30)                              |
+---------------------------------------------------------------+
|                    [ Back ]   [ Next → ]                      |
+---------------------------------------------------------------+
```

---

# 🟦 **5. Create Alert — Step 4: Trigger Settings**

```
+---------------------------------------------------------------+
|  CREATE ALERT  (4/4)  —  Trigger Settings                     |
+---------------------------------------------------------------+
| Trigger Mode:                                                 |
|   (•) Once                                                    |
|   ( ) Once per bar (per timeframe)                            |
|   ( ) Every time condition is true                            |
|            Throttle: at most once every [ 15 ] minutes        |
|                                                               |
| Alert Lifetime:                                               |
|   (•) No expiry                                               |
|   ( ) Expire on [ 2025-03-01 15:30 ]                          |
|                                                               |
| Test (optional): [Run condition on last bar]                  |
| Result:                                                       |
|   INFY → FALSE (RSI=44.3)                                     |
|   TCS  → TRUE  (RSI=28.2)                                     |
|                                                               |
|                 [ Back ]   [ Save Alert ]                     |
+---------------------------------------------------------------+
```

---

# 🟦 **6. Edit Alert — Same Screens, Pre-filled**

When editing:

* All steps are identical to creation
* Values are pre-filled
* Add “Disable/Enable” button on header

---

# 🟦 **7. Custom Indicators — Wireframe**

```
+---------------------------------------------------------------+
|  CUSTOM INDICATORS                                            |
+---------------------------------------------------------------+
| [ + Create Custom Indicator ]                                 |
+---------------------------------------------------------------+
| Name              | Params           | Timeframes | Enabled   |
|----------------------------------------------------------------|
| SWING_SCORE_1D    | src,len_atr,len_vol | 1d      |   ✓       |
| VALUE_SCORE       | src,window          | 1d       |   ✓       |
+---------------------------------------------------------------+
```

### Create Custom Indicator Popup

```
+---------------------------------------------------------------+
|  CREATE CUSTOM INDICATOR                                      |
+---------------------------------------------------------------+
| Name: [ SWING_SCORE_1D ]                                      |
| Description: [ Measures swinginess of price ]                 |
|                                                               |
| Parameters:                                                   |
|   Name       | Type           | Default | X                   |
|   ---------------------------------------------------------   |
|   src        | price_series   | close   | ✕                   |
|   len_atr    | int            | 14      | ✕                   |
|   len_vol    | int            | 20      | ✕                   |
|                                                               |
| Formula:                                                      |
|  [ ATR(src,len_atr,"1d") / PRICE("1d") * 100                  |
|    + StdDev(returns(src,"1d"), len_vol) * 100            ]    |
|                                                               |
| Expression Preview:                                           |
| ATR(src,14,"1d")/PRICE("1d")*100 + StdDev(returns(src,"1d"),20)*100 |
|                                                               |
|                     [ Save ]   [ Cancel ]                     |
+---------------------------------------------------------------+
```

---

# 🟦 **8. Alert Event Feed**

```
+---------------------------------------------------------------+
|  ALERT EVENTS                                                 |
+---------------------------------------------------------------+
| Time            | Alert Name               | Symbol | Value   |
|---------------------------------------------------------------|
| 10:32:14        | RSI Oversold 1H          | TCS    | TRUE    |
| 10:15:21        | Breakout w/ Volume Spike | INFY   | TRUE    |
+---------------------------------------------------------------+
```

Include filters: per alert, per symbol, last 24h / 7d, etc.

---

# 🟦 **9. How These Wireframes Map to DSL**

* Every row → `(LHS OP RHS)`
* Join column → AND/OR
* Parentheses come from explicit grouping (Phase 2)
* Variables → internal function calls like `RSI(close,14,"1h")`
* Custom indicators → function calls like `SWING_SCORE_1D(close)`

**UI keeps users safe**
**DSL keeps your engine powerful and composable**

---
