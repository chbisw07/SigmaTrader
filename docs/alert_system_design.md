# Alert System Design – Complex Indicator Expressions (Q&A)

## Question

Without involving AI for now, design or redesign the alerts system so that it supports complex expressions. I want to:

- Compare indicators to values and to other indicators.
- Combine conditional expressions with `AND` / `OR` operators and allow parentheses.
- Allow each indicator to use its own timeframe (e.g. `RSI(14, 1D)` with `SMA(20, 1D)` and `SMA(50, 1D)`, `Volatility(50, 1D)` etc.).
- Potentially support two usage modes:
  1. The user writes text expressions like:
     - `(RSI(14, 1D) > 80) AND (SMA(20, 1D) CROSS_ABOVE SMA(50, 1D))`
  2. The UX allows building expressions equivalent to #1 without writing text directly.

The idea is that if our core design is solid and deterministic, an AI layer added later will be more useful and less risky.

## Answer / Proposed Design

### 1. Goals

The alert engine should:

- Compare indicators to:
  - Numeric constants (e.g. `RSI(14) > 80`).
  - Other indicators (e.g. `SMA(20) CROSS_ABOVE SMA(50)`, `PRICE > VWAP`).
- Allow indicator-specific timeframes:
  - `RSI(14, 15m)` and `SMA(50, 1D)` in the same rule.
- Support full boolean logic:
  - `AND`, `OR`, `NOT`.
  - Parentheses and nested expressions: `((A AND B) OR (C AND D)) AND E`.
- Remain fully deterministic and debuggable on top of the existing OHLCV store.
- Expose a single core model that can be used both by:
  - A text expression DSL.
  - A visual/builder UX.

### 2. Core Domain Model

#### 2.1 Indicator specification

Represent any indicator as a structured `IndicatorSpec`:

- `kind` – the indicator type:
  - `PRICE`, `RSI`, `SMA`, `EMA`, `VOLATILITY`, `ATR`, `VWAP`, `PERF_PCT`, `VOLUME`, `VOLUME_AVG`, etc.
- `timeframe` – e.g. `1m`, `5m`, `15m`, `1H`, `1D`, `1W`, `1M`.
- `params` – indicator-specific parameters:
  - `period` (RSI(14), SMA(20)).
  - `window` (VOLATILITY(50)).
  - `source` (`close`, `open`, `high`, `low`), etc.

This makes each indicator self-contained with its timeframe and parameters, independent of the rule as a whole.

#### 2.2 Expression AST for rules

Each alert rule is an expression tree composed of three node types:

- **Operands**
  - `INDICATOR` – wraps an `IndicatorSpec`.
  - `NUMBER` – a numeric literal (threshold).

- **Comparison node**
  - `COMPARISON` with:
    - `left: Operand`.
    - `operator: ComparisonOperator`.
    - `right: Operand`.
  - `ComparisonOperator` includes:
    - `GT`, `GTE`, `LT`, `LTE`, `EQ`, `NEQ`.
    - `CROSS_ABOVE`, `CROSS_BELOW` (indicator-to-indicator only).

- **Logical nodes**
  - `LOGICAL` – has:
    - `op: AND | OR`.
    - `children: ExpressionNode[]` (>= 2).
  - `NOT` – wraps a single `child: ExpressionNode`.

Parentheses in the user’s expression correspond to nesting of `LOGICAL`/`NOT` nodes. For example:

```text
(RSI(14, 1D) > 80) AND (SMA(20, 1D) CROSS_ABOVE SMA(50, 1D))
```

maps to:

- A top-level `LOGICAL(AND)` node whose children are:
  - A `COMPARISON` (`RSI(14, 1D) > 80`).
  - A `COMPARISON` (`SMA(20, 1D) CROSS_ABOVE SMA(50, 1D)`).

This AST is expressive enough for arbitrarily complex boolean structures.

#### 2.3 Rule model

Extend the `IndicatorRule` model to include:

- `symbol`, `exchange` and/or `universe` (HOLDINGS, custom watchlist, etc.).
- `expression_json` – the serialized `ExpressionNode` tree.
- `trigger_mode` – `ONCE`, `ONCE_PER_BAR`, `EVERY_TIME`.
- Optional metadata – `primary_timeframe`, `name`, `notes`, `expiration`, etc.

Persist `expression_json` as a JSON column. Existing simple rules can be represented as a single `COMPARISON` node to ease migration.

### 3. Evaluation Pipeline

1. **Collect required indicators**
   - Walk the `expression_json` tree and gather all `IndicatorSpec`s referenced as operands.

2. **Resolve OHLCV requirements**
   - For each `IndicatorSpec`, derive:
     - The underlying candle timeframe (`1D`, `15m`, etc.).
     - The number of lookback bars needed (e.g. RSI(14) → 15, SMA(50) → 50, VOLATILITY(50) → 51).

3. **Fetch OHLCV and compute indicators**
   - For each `(symbol, timeframe)` pair:
     - Use the existing `load_series` / `ensure_history` logic to get candles.
     - Compute indicator values for all required `IndicatorSpec`s.
     - Cache the latest value (and previous value where needed for `CROSS_*` or “rising/falling” semantics).

4. **Evaluate the expression tree**
   - Implement `evaluate(node: ExpressionNode) -> bool`.
   - For `COMPARISON`:
     - Resolve `left` and `right` operands to numeric values.
     - If values are unavailable (insufficient history), treat the comparison as `false` or “not ready”.
     - Implement:
       - `GT`, `GTE`, `LT`, `LTE`, `EQ`, `NEQ` as normal numeric comparisons.
       - `CROSS_ABOVE`/`CROSS_BELOW` by comparing `(prev_left, left)` vs `(prev_right, right)`.
   - For `LOGICAL`:
     - Implement `AND` / `OR` with short-circuit evaluation.
   - For `NOT`:
     - Invert the child’s result.

5. **Apply trigger semantics and side effects**
   - If the expression evaluates to `true` for a given bar:
     - Respect `trigger_mode`:
       - `ONCE` – fire once, then disable or mark satisfied.
       - `ONCE_PER_BAR` – fire at most once per bar for each symbol.
       - `EVERY_TIME` – fire on every evaluation where conditions are true.
     - Create an `Alert` row and, if configured, enqueue an `Order` (e.g., `SELL_PERCENT`, `BUY_QUANTITY`), as in the current system.

This evaluation remains purely deterministic and based on the stored OHLCV data.

### 4. Text Expression DSL (Option 1)

Define a small, strict DSL that maps directly to the AST:

- **Indicators**
  - `RSI(14, 1D)`
  - `SMA(20, 1D)`
  - `SMA(50, 1D)`
  - `VOLATILITY(50, 1D)`
  - `PRICE(1D)` (shorthand for daily close).
  - `ATR(14, 1D)`, etc.

- **Comparison operators**
  - `>`, `>=`, `<`, `<=`, `==`, `!=`
  - `CROSS_ABOVE`, `CROSS_BELOW`

- **Logical operators**
  - `AND`, `OR`, `NOT`, parentheses `( )`.

- **Examples**

  ```text
  (RSI(14, 1D) > 80)
    AND (SMA(20, 1D) CROSS_ABOVE SMA(50, 1D))

  (PRICE(15m) > SMA(20, 15m))
    AND (RSI(14, 15m) < 60)
    AND (VOLATILITY(50, 1D) < 2.0)

  (RSI(14, 1D) < 30 OR PRICE(1D) < SMA(200, 1D))
    AND NOT (VOLATILITY(20, 1D) > 5.0)
  ```

**Parsing strategy:**

- Tokenize identifiers, numbers, parentheses, commas, operators and keywords.
- Use a precedence-aware parser (recursive descent is sufficient):
  - Highest: indicator calls and numbers.
  - Then comparisons.
  - Then `NOT`.
  - Then `AND`.
  - Then `OR`.
- Construct the `ExpressionNode` tree and validate:
  - Known `IndicatorKind` and `Timeframe`.
  - `CROSS_*` must compare two indicators, not indicator vs number.

You can expose this DSL in the UI as an “Advanced expression” box with:

- Inline validation (success/error).
- A read-only preview of the parsed structure in friendly language.

### 5. Visual Builder UX (Option 2)

Provide a “no-code” way to build the same expression tree.

#### 5.1 Condition rows

Each condition row corresponds to a `COMPARISON` node and lets the user specify:

- **Left side**
  - Indicator selector (Price, RSI, SMA, EMA, ATR, Volatility, etc.).
  - Timeframe selector for that indicator.
  - Indicator parameters (period/window).

- **Operator**
  - `>`, `>=`, `<`, `<=`, `==`, `!=`.
  - `Crossing above`, `Crossing below`.

- **Right side**
  - Switch between:
    - Numeric value (e.g. `80`).
    - Another indicator (e.g. `SMA(50, 1D)`).

#### 5.2 Grouping and boolean logic

To support parentheses and complex expressions:

- Organize conditions into **groups**, each with its own logic (`AND` or `OR`).
- Allow nested groups:
  - “Add group” creates a child `LOGICAL` node.
  - Groups are visually indented and can themselves contain conditions and subgroups.
- Optional “NOT” flag on a group or condition to wrap it in a `NOT` node.

Internally:

- The group tree directly maps to nested `LOGICAL` / `NOT` nodes.
- Editing the groups modifies the underlying AST.

#### 5.3 Expression preview and round-trip

- At the bottom of the builder, show a textual preview generated from the AST (effectively a DSL string).
- When loading an existing rule:
  - Deserialize `expression_json`.
  - Render groups and rows back into the builder.

This allows both a structured UX and (optionally) a raw DSL editor to coexist and always stay in sync because both operate on the same AST.

### 6. Strategy Examples

With the above design, the following strategies become straightforward:

- **Overbought trend-following with low volatility:**

  ```text
  (RSI(14, 1D) > 80)
    AND (PRICE(1D) > SMA(50, 1D))
    AND (VOLATILITY(50, 1D) < 2.5)
  ```

- **Bullish crossover with long-term confirmation:**

  ```text
  (SMA(20, 1D) CROSS_ABOVE SMA(50, 1D))
    AND (PRICE(1D) > SMA(200, 1D))
  ```

- **Intraday pullback in an uptrend:**

  ```text
  (PRICE(15m) < SMA(20, 15m))
    AND (PRICE(1D) > SMA(50, 1D))
    AND (RSI(14, 15m) < 40)
  ```

The same machinery covers many more combinations simply by adding new `IndicatorKind`s and operators.

### 7. Suggested Implementation Sequence

1. **Backend**
   - Introduce `IndicatorSpec` and `ExpressionNode` types alongside the current `IndicatorCondition`.
   - Implement indicator evaluation using OHLCV store, with support for `CROSS_*`.
   - Add `expression_json` to `IndicatorRule`.
   - Map existing simple rules to single-node `COMPARISON` expressions for backward compatibility.

2. **Minimal DSL support**
   - Implement the text parser and validation.
   - Add an “Expression” or “Advanced” tab in the alert dialog using this DSL.

3. **Visual builder**
   - Build the group + row UI that manipulates the AST directly.
   - Keep DSL preview in sync for transparency.

Once this deterministic design is in place, an AI/LLM layer can later be added purely as a helper (to generate or explain `expression_json`), without complicating or weakening the core alert engine.

---

### 8. Strategies – Reusable Alert Templates

To make complex alerts easier to reuse and share, we introduce a first-class **Strategy** concept separate from individual alert rules.

#### 8.1 Strategy vs. Rule

- **Strategy**
  - A reusable *template* that defines *what* conditions should be met.
  - Holds the expression and descriptive metadata, but not the specific symbol (unless scoped locally).
  - Example fields:
    - `id` / `code` (e.g. `ST001-G`).
    - `name` – short label: “RSI overbought with trend filter”.
    - `comments` – free-form explanation and guidance.
    - `dsl_expression` – the human-readable DSL string.
    - `expression_json` – parsed AST for evaluation.
    - `scope` – `GLOBAL` or `LOCAL` (see below).
    - Optional defaults – suggested trigger mode, action type, default timeframes.

- **IndicatorRule (Alert rule)**
  - A concrete application of a strategy (or custom ad-hoc logic) to:
    - A single symbol, or
    - A basket/group of symbols (future extension).
  - References:
    - `strategy_id` (nullable – rules can still be fully custom).
    - `target_type` / `target_id` (symbol vs group; see section 9).
    - `expression_json` – copied from the strategy at creation time, but can be overridden per rule if needed.

This separation allows:

- Predefined, curated strategies for novice users.
- Local tweaks for a specific symbol without changing the global template.
- Reporting and filtering by strategy (e.g. “show all rules using ST001-G”).

#### 8.2 Strategy scope: Local vs Global

Introduce a strategy `scope`:

- `GLOBAL`
  - Available for use when creating an alert for **any** symbol.
  - Intended for generic patterns such as:
    - “Daily RSI overbought with price above 50D SMA and low volatility.”
    - “Intraday pullback in a daily uptrend.”
  - When used to create a rule for `BSE`, the new rule references `strategy_id = ST001-G`.
  - When later creating an alert for `CAMS`, the same global strategy `ST001-G` appears in the strategy picker.

- `LOCAL`
  - Strategy is conceptually tied to a particular symbol (or group).
  - Typical use: you experimented with some alerts on `BSE` and want to save the configuration as a named strategy visible only in the context of `BSE`.
  - Implementation:
    - Add `symbol` / `exchange` fields (or `target_type = SYMBOL`, `target_id`) on the `Strategy` record.
    - Filter the strategy picker to include:
      - All `GLOBAL` strategies.
      - Any `LOCAL` strategies whose target matches the current symbol.

From a UX point of view, the “Save as strategy” flow in the alert dialog can ask:

- Strategy name and comments.
- Scope: “Local (only for this symbol)” vs “Global (available for all symbols)”.

#### 8.3 Strategy CRUD and presets

**CRUD endpoints / APIs**

- `GET /api/strategies` – list strategies with filters:
  - By scope (`GLOBAL`, `LOCAL`).
  - By availability for symbol (e.g. `symbol=BSE`).
- `POST /api/strategies` – create a new strategy from:
  - DSL string, or
  - Existing AST (from the visual builder).
- `PUT /api/strategies/{id}` – update name/comments/DSL, with AST re-parsed.
- `DELETE /api/strategies/{id}` – soft-delete or archive.

**Preset strategies**

- Seed the database with a set of `GLOBAL` strategies, for example:
  - `ST001-G` – Overbought trend-following with low volatility.
  - `ST002-G` – Bullish crossover with long-term confirmation.
  - `ST003-G` – Intraday pullback in a daily uptrend.
- Each preset strategy stores:
  - Friendly `name` and `comments`.
  - `dsl_expression` and `expression_json`.
- In the alert dialog, a “Choose a strategy” dropdown shows:
  - Predefined strategies grouped under “Built-in”.
  - User-created strategies under “My strategies”.

When a user selects a strategy:

- The dialog populates the builder fields from `expression_json`.
- The user can:
  - Accept it as-is (pure reuse), or
  - Customize it for this rule and optionally save as a new strategy.

---

### 9. Alert Targets – Symbols and Baskets

Today, alerts are per-symbol. To support baskets/groups, the rule model should gain explicit **target** fields:

- `target_type` – one of:
  - `SYMBOL` – single symbol in a specific exchange.
  - `GROUP` – future extension for baskets.
  - (Optional) `UNIVERSE` – entire holdings or a custom screener.
- `target_id` – references:
  - For `SYMBOL`: a logical instrument identifier (or symbol/exchange pair).
  - For `GROUP`: a `Basket`/`Group` record.

#### 9.1 Basket / group concept (future-ready)

Define a `Basket` model (can be added later when needed):

- `id`, `name`, `description`.
- `source` – e.g. `HOLDINGS`, `WATCHLIST`, `CUSTOM`.
- `members` – set of `(symbol, exchange)` pairs.

When a rule targets a basket:

- The evaluation engine iterates each member symbol and evaluates the expression using that symbol’s market data.
- For each symbol that matches, alerts (and optional orders) are created just as they are for symbol-targeted rules.

The strategy itself remains **symbol-agnostic**; only the rule’s `target_type/target_id` change.

---

### 10. Alerts Management UX

To manage alerts at scale, a dedicated **Alerts** page is recommended.

#### 10.1 Alerts list page

Add a new route, e.g. `/alerts`, with a DataGrid summarizing all rules and recent activity. Suggested columns:

- `Symbol / Target`
  - For `SYMBOL` targets: `SYMBOL / EXCHANGE` (e.g. `BSE / NSE`).
  - For `GROUP` targets: basket name plus a count of members.
- `Strategy`
  - Strategy name/code (e.g. `ST001-G – RSI overbought`).
  - A badge indicating `GLOBAL` vs `LOCAL`.
- `Expression`
  - Short text summary of the AST (same as DSL or a condensed version).
- `Status`
  - `ACTIVE`, `PAUSED`, `SATISFIED`, `ERROR`.
- `Trigger Mode`
  - `Once`, `Once per bar`, `Every time`.
- `Created at`
- `Last triggered at`
- `Trigger count` – number of times alert fired.
- `Last action`
  - e.g. “Queued SELL 10%”, or “Alert only”.

Actions per row:

- `Edit` – opens the alert dialog with current rule/strategy loaded.
- `Pause` / `Resume`.
- `Delete`.
- `View log` – drill-down into recent firings and associated orders.

Filters:

- By symbol / exchange.
- By strategy.
- By status.
- By timeframe(s) or indicator types (optional).

#### 10.2 Alert detail view

For deeper inspection, an optional detail drawer or page can show:

- The full DSL and structured tree.
- Historical triggers (timestamp, symbol, value snapshot).
- Linked orders (IDs, status, fill price).

---

### 11. Holdings Integration – Alert Awareness in Context

Since holdings are your primary workspace, alerts should be visible and accessible directly from the Holdings view.

#### 11.1 Alert chip near symbol

In the Holdings grid:

- Add an **Alert chip/icon** near the symbol (or inside the existing “Alerts” column) that indicates:
  - No active rules → greyed out or empty icon.
  - One or more active rules → colored chip showing count (e.g. `ALERT (2)`).
- Clicking the chip:
  - Opens a small panel/modal listing active rules for that symbol:
    - Strategy name (if any).
    - Short expression summary.
    - Status and trigger mode.
  - Provides actions:
    - `Edit` / `Pause` / `Delete`.
    - `Add new alert` (reusing the existing “Create indicator alert” dialog).

This gives at-a-glance feedback: “Does this position have live alerts watching it?”

#### 11.2 Alerts tab vs. dedicated page

There are two options for where users manage alerts:

1. **Dedicated Alerts page (recommended)**
   - Central place for all alerts regardless of symbol or origin.
   - Works well for scanning, filtering and bulk operations.

2. **Alerts tab within Holdings**
   - A secondary tab or section under the Holdings view that lists alerts **only for current holdings**.
   - Could reuse the same grid as the main Alerts page but pre-filtered to `target_type = SYMBOL` and symbols in holdings.

Suggested approach:

- Implement the **dedicated Alerts page** as the primary management surface.
- Integrate alert awareness in Holdings via:
  - Alert chips/icons per symbol.
  - The existing “Alert” button and per-symbol modal.
  - Optionally, a “View alerts for holdings” filter preset on the Alerts page rather than a full extra tab.

This keeps the Holdings page focused on positions and quick access, while the Alerts page becomes the full control center.

---

### 12. Putting It All Together

With these extensions, the alerts system consists of:

- A **deterministic core engine**:
  - Expression AST with rich indicator support and boolean logic.
  - Evaluation built on the OHLCV store and indicator library.

- Two complementary authoring experiences:
  - **Text DSL** – for users who prefer typing expressions and for copy/paste or documentation.
  - **Visual builder** – a no-code UI that manipulates the same AST.

- **Strategies** as reusable templates:
  - Global and local scopes.
  - CRUD APIs and preset strategies to help novices get started.
  - Rules referencing strategies but still customizable per symbol or basket.

- **Flexible targets**:
  - Rules applied to single symbols today.
  - Future support for baskets / groups by adding `target_type = GROUP`.

- **Management UX**:
  - Dedicated Alerts page with a rich DataGrid.
  - Contextual integration into Holdings via alert chips and the existing “Alert” actions.

This design keeps the heart of the system—the alert logic—clean, expressive and testable, while making it easier to grow towards:

- Advanced indicator combinations and strategies.
- Group- and portfolio-level alerts.
- Future AI assistance that simply reads and writes the same strategy/AST structures without changing how alerts are actually executed.

---

### 13. Implementation Notes and Edge Cases

To keep implementation predictable and maintainable, a few additional details are worth calling out.

#### 13.1 Rule scheduling and evaluation cadence

- The existing scheduler that evaluates indicator rules **periodically in IST** should be refined to:
  - Use a base tick suitable for the smallest timeframe you plan to support (e.g. 1m or 5m).
  - On each tick, load active rules and:
    - Compute, for each rule, its primary timeframe(s) from the indicators in its AST.
    - Optionally skip evaluation if the underlying bar for the primary timeframe has not changed since the last run (avoid re-triggering on the same candle).
- Store per-rule, per-target metadata such as:
  - `last_evaluated_at`.
  - `last_evaluated_bar_time` for each relevant timeframe.
- For `ONCE_PER_BAR`:
  - Track `last_trigger_bar_time` so a rule does not fire more than once per bar per symbol, even if evaluated multiple times within that bar’s duration.

#### 13.2 Strategy versioning vs. rule snapshots

- When a rule is created from a strategy:
  - Copy the strategy’s `expression_json` into the rule as a **snapshot**.
  - Store `strategy_id` and optionally `strategy_version` on the rule.
- When a strategy is edited later:
  - Existing rules continue to use their stored snapshot; they do **not** auto-update unless you explicitly implement a “sync rules to latest strategy version” flow.
  - This avoids surprising behavior where live alerts silently change because a shared strategy was edited.

#### 13.3 Ownership, users, and multi-tenancy

Even though the current setup is single-user, it is helpful to model ownership cleanly:

- Add `user_id` (or `owner_id`) to:
  - `Strategy`.
  - `IndicatorRule`.
  - `Basket`/`Group` (when introduced).
- Built-in preset strategies can be marked with:
  - `owner_id = NULL` and a `is_builtin = true` flag, or
  - A dedicated “system” user.
- All APIs should filter by the current user where appropriate, while still exposing read-only built-in strategies.

This keeps the system ready for future multi-user or role-based scenarios without changing the core design.

#### 13.4 Observability and debugging

To make alerts more trustworthy in live trading:

- Log, per evaluation:
  - Raw indicator values used at the decision point.
  - Final expression truth value and the reason for firing (e.g., which comparison flipped from false to true).
- Surface summarized information in:
  - The alert detail view (section 10.2).
  - Optionally, the existing System Events page for high-level monitoring.

These hooks make it much easier to diagnose discrepancies or unexpected triggers.
