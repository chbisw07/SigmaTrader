# SigmaTrader – Stock Screener & Advanced Filters

---

## 1. Motivation and current behaviour

**Question**  
Currently the Holdings page has an “Advanced filters” bar with simple row‑based conditions such as:

- Column: `Symbol`  
- Operator: `contains`  
- Value: `XYZ`

Multiple conditions can be added, and they are combined with `AND`. This works for quick, single‑condition filtering, but it feels limited compared to what we can do with all the analytics we now have (indicators, risk columns, correlation clusters, alert DSL, etc.).

I’m thinking of replacing / evolving this into a *stock screener*:

- The screener will screen the current Holdings (or a broader universe later) using the current advanced‑filter conditions.  
- It will also support the indicator/alert DSL expressions.  
- I want the screened stocks to be selectable.  
- I want to apply **buy/sell** actions to the screened stocks.  
- I want to apply **alerts** (indicator rules / strategies) to the screened stocks.

Please analyse the feasibility, fill any gaps, and expand this idea into a full‑fledged feature that reuses what we already have.

**Answer (high‑level)**  
Turning the current advanced filters into a richer stock screener is both feasible and a natural evolution for SigmaTrader. Most of the heavy pieces already exist:

- We already compute a rich set of metrics per holding (PnL, RSI, ATR, volatility, clusters, etc.).
- We already have an alert **DSL** and AST engine on the backend for indicator‑based rules.
- We already have batch‑style flows (manual order queue, alerts per universe like HOLDINGS).

The screener would sit “on top” of these pieces and provide:

- A more expressive filter UI (multi‑row visual builder *and* optional DSL text mode).  
- A way to *persist* screener definitions (like saved filters/queries).  
- Batch actions: “Create BUY orders for all selected rows”, “Attach strategy ST004‑G to all selected rows”, etc.

Below is a more detailed design.

---

## 2. Conceptual model – from filters to a screener

### 2.1 Current advanced filters

Today’s advanced filters are:

- **Scope**: only the currently loaded Holdings grid.  
- **Structure**: a flat list of conditions combined with `AND`.  
- **Operators**: basic column comparisons (symbol contains, numeric `>`, `<`, `=` etc.).  
- **Behaviour**: purely client‑side; the grid re‑filters in memory.

This is simple and fast but cannot:

- Express OR / grouped logic with parentheses.  
- Compare *columns to columns* (e.g. RSI(14) vs cluster avg).  
- Express temporal or indicator logic (e.g. RSI(14, 1D) < 30 AND 1M PnL% < ‑15).  
- Trigger any actions other than visual filtering.

### 2.2 Screener as a first‑class object

The proposed screener would introduce a new concept:

- **Screener definition** = `(universe, expression, display settings, attached actions)`, where:
  - `universe` – which symbols to evaluate (e.g. `HOLDINGS`, `WATCHLIST_X`, or a custom universe later).
  - `expression` – filter logic, either:
    - Built via a visual multi‑row builder (extended version of today’s advanced filters), or
    - Written as a **DSL expression** using the indicator/alert DSL (e.g. `RSI(14, 1D) < 30 AND VOLATILITY(20) > 2`).
  - `display settings` – which columns/views to show when this screener is active (e.g. Risk view vs Default).
  - `attached actions` – optional default batch actions (e.g. “default BUY sizing = 1% of portfolio”).

Screeners can be:

- **Ad‑hoc** (unsaved) – e.g. temporary filters for the session.  
- **Saved** – persisted per user and selectable from a dropdown (“Momentum oversold”, “High volatility small‑caps”, etc.).

---

## 3. UI/UX sketch

### 3.1 Screener panel replacing / extending advanced filters

Instead of a simple “Advanced filters” bar, Holdings would have a **Screener** panel with two modes:

1. **Builder mode (no‑code)**  
   - Rows: `Column | Operator | Value` with `+ Add condition`.  
   - Support for:
     - `AND` / `OR` between rows.  
     - Optional grouping with parentheses (e.g. `(A AND B) OR C`).  
     - Column‑to‑value comparisons (as today), but also:
       - Column‑to‑column (e.g. `1M PnL %` vs `1Y PnL %`).
       - Metric vs *cluster* metrics (e.g. “Stock’s beta > cluster avg beta” – phase‑2).
   - Shares patterns with the alert simple‑builder UI to avoid learning two different syntaxes.

2. **DSL mode (power‑user)**  
   - Text area that accepts the *alert DSL* extended with:
     - Direct reference to Holdings metrics:  
       `PCT_PNL_1M < -10 AND RSI(14, 1D) < 30 AND VOL_20D > 2.0`
     - Column‑like aliases for readability:  
       `PCT_PNL_1M` ↔ `1M PnL %`, `DD_FROM_PEAK` ↔ drawdown, etc.
   - Live parsing/validation with errors shown inline (we can reuse the existing DSL parser and expression AST).
   - A one‑click toggle to copy the builder configuration to DSL (and vice versa, when round‑tripping is feasible).

Both modes:

- Produce a single canonical expression (AST) under the hood.  
- Can be saved as a named *screener*.

### 3.2 Screened results and selection

The Holdings grid already supports:

- Column selection and presets (Default view, Risk view, etc.).  
- Row selection via checkboxes (MUI DataGrid).  
- Batch‑style information (per‑row actions, but not yet batch actions).

With the screener active:

- The grid shows only rows that satisfy the screener expression.  
- The row‑selection checkboxes remain available; the user can:
  - Select all filtered rows.
  - Deselect specific names manually.

Above the grid (or in a small toolbar), we can expose **batch actions**:

- “Create BUY orders for selected”  
- “Create SELL orders for selected”  
- “Attach indicator alerts / strategy template…”

These batch actions will reuse:

- The existing **Holdings Buy/Sell dialog** (for sizing rules).  
- The existing **indicator alert dialog** (for strategy/alert templates).  
- The **manual order queue** semantics (orders created as WAITING).

We can design this so that:

- Clicking a batch action opens a compact configuration dialog (e.g. “BUY 1% of portfolio each, via MARKET, CNC, with bracket re‑entry GTT enabled”), then:
  - The backend creates one manual order per selected symbol, using the same sizing rules we already have.  
- For alerts:
  - Select a strategy template (e.g. ST004‑G PVT bullish correction) and create indicator rules for all selected symbols in one go.

---

## 4. Backend considerations & feasibility

### 4.1 Reusing the DSL and indicators

We already have:

- An alert **DSL parser** → AST.  
- An **indicator evaluation** engine for rules (RSI, MA, volatility, PVT, etc.).  
- Per‑symbol Holdings metrics computed in the backend and exposed via APIs.

For the screener:

- **DSL expressions** can be evaluated either:
  - Directly on Holdings metrics already present in the API payload (fast, no extra data fetch), or  
  - Via the indicator engine for expressions that need historical series not yet exposed in Holdings (e.g. complex multi‑timeframe conditions).
- The same AST/evaluator used for alerts can be used in a “stateless” way for screening:
  - Instead of scheduling over time, we simply:
    - Load current metrics for the universe.
    - Evaluate the expression for each symbol.
    - Return `true/false` plus any derived values (e.g. indicator snapshots).

This reuse keeps implementation cost relatively low and behaviour consistent between *alerts* and *screeners*.

### 4.2 Universe and scaling

Phase‑1 can limit the screener to:

- **Universe = HOLDINGS** – only your current live positions.  
- This is small (order of 100 symbols), so evaluating DSL expressions or multiple filter conditions is cheap.

Later phases can expand to:

- Watchlists or a broader NSE/BSE universe by querying the `instruments` table and the OHLCV store.

### 4.3 Batch actions and risk

Batch BUY/SELL from a screener must respect:

- Per‑strategy risk settings (max order value, max daily loss, etc.).  
- Broker and margin constraints.

Fortunately, we already route manual orders through a risk engine. The screener batch actions can:

- Create the same `ManualOrderCreate` payloads as the Holdings dialog, one per symbol.  
- Let the backend risk checks accept/reject each order independently.  
- Return a summary: “15 orders created, 3 rejected due to risk settings” and log details to `system_events`.

For alerts:

- Each batch alert creation maps to `indicator_rules` rows linked to a chosen strategy template (GLOBAL or LOCAL).

---

## 5. My opinion & suggested scope for first iteration

1. **Feasibility** – high.  
   - The core ingredients (metrics, DSL, alerts, grids, manual queue) already exist.  
   - The main work is UI/UX and wiring a *screening* API that evaluates expressions against holdings.

2. **Value** – very high.  
   - A screener turns your Holdings page into a small “quant terminal”: you can express ideas like:
     - “Show holdings where RSI(14) < 30 AND 1M PnL % < -15 AND ATR(14) % > 3”.  
     - “Show clusters where correlation is low but volatility is high”, etc.
   - Being able to immediately:
     - Create batch bracket orders, or  
     - Attach strategies/alerts to the screened subset  
     fits perfectly with how you already trade via queues and rules.

3. **Recommended Phase‑1 scope**
   - Keep universe = HOLDINGS.  
   - Provide:
     - Enhanced builder with AND/OR and multiple rows.  
     - DSL text mode using the existing indicator DSL (restricted to metrics we already compute).  
     - Screening applied client‑side first (on the Holdings payload) to reduce backend changes.  
     - Batch **alert attachment** (easiest) and **batch manual order creation** using the existing dialog patterns.
   - Defer full “universe‑wide” scanning and heavier factor‑model logic to later phases.

In short: replacing the current advanced filters with a true screener is a natural, high‑leverage next step. It is technically feasible, aligns well with your DSL/alerts architecture, and can greatly improve how you select and act on opportunities across your holdings.

