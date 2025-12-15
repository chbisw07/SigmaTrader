# Holdings Refactoring: One `UniverseGrid`, Multiple Universes

This document captures the current conversation (Q&A) plus a concrete, detailed refactoring plan to evolve SigmaTrader from a “Holdings page” into a reusable **Universe-driven** grid experience.

The goal is to reuse the same rich datagrid + selection + bulk actions + alerts across:
- Holdings (from Kite / Zerodha)
- Groups (Watchlists, Baskets, Holdings-views)
- Portfolios (realized baskets; effectively a holdings-view with extra metadata)

---

## 1) Q&A (captured from discussion)

### Q: Should `% of portfolio` exist for bulk buy/sell?
**A:** In bulk mode, `% of portfolio` is ambiguous if interpreted as “apply the same % to each symbol”. It can be made meaningful only if redefined as **total % across selected symbols** (i.e., convert to a total budget, then allocate). To reduce ambiguity and keep UX crisp, we remove it for bulk.

### Q: For non-holdings universes, should SELL be allowed?
**A:** **Yes.** Zerodha allows MIS shorting, so SELL should be allowed even if the symbol is not currently in holdings, as long as product/order-type rules permit it.

### Q: What is the mental model for watchlist, basket, portfolio, holdings-view?
**A:**
- **Watchlist**: A group of symbols. Symbols may or may not be held. No concept of avg price, invested amount, holdings-derived P&L, etc.
- **Basket**: Conceptual construct derived from watchlist. It has per-symbol **qty** and **reference price at basket creation**, and supports derived metrics like “amount required”, “P&L since creation”, “today P&L”, etc. It can support allocations (equal, weights, amount-based).
- **Portfolio**: Realized version of a basket (an instance). The “creation price” becomes buy reference price. Portfolio symbols are **expected** to be in Zerodha holdings in the common case, but this is not mandatory: a portfolio may be sourced from elsewhere and used purely to discover opportunities. When a portfolio symbol is not held, holdings-derived metrics simply remain blank.
- **Holdings-view**: A group that is a subset of holdings.

### Q: Alerts should be global per symbol or contextual per group?
**A:** Alerts should be **global per symbol**.

### Clarification: Alerts vs indicators vs strategies vs screeners
**Intent model (recommended):**
- **Indicator**: A computed number/series (RSI, MA, etc.).
- **Screener**: A query that selects a set of symbols (a universe filter) at a point in time.
- **Alert**: A rule attached to a symbol that triggers a notification and/or an action (strategy).
- **Strategy**: A templated action plan that can be executed when an alert triggers (e.g., create BUY order, set bracket GTT, etc.).

**Key principle:** The UI should keep intent clear:
- “I want to find symbols” → screener
- “I want to be notified / take action for symbol X” → alert (global)
- “I want to execute an action across a selection” → bulk action

---

## 2) Where we are now

Today, the rich UX (filters/screener, selection, bulk buy/sell, create group, alert button per row, etc.) lives primarily in:
- `frontend/src/views/HoldingsPage.tsx`

Groups exist in:
- `frontend/src/views/GroupsPage.tsx`

But the Groups page currently uses a different grid structure and doesn’t reuse the Holdings grid behavior and the bulk tooling.

**Observed risks (current state):**
- `HoldingsPage.tsx` is growing into a mega-file, making it harder to reason about and reuse.
- Similar “symbol list” behavior (selection, bulk actions, alerts) is likely to get duplicated across pages.
- Domain concepts (watchlist/basket/portfolio/holdings-view) are represented as “groups”, but the UX doesn’t yet treat them as first-class “universes”.

---

## 3) Where we want to go (target architecture)

### Thesis
Build a single reusable grid component, called **`UniverseGrid`**, that can render “a list of symbols” with optional “overlays” (holdings, group membership, basket metadata, etc.) and consistent actions (buy/sell, bulk buy/sell, alerts, create group).

### Key abstractions

#### 3.1 Universe
A **Universe** is a named set of symbols.

Examples:
- `Holdings (Zerodha)` → Universe ID: `holdings`
- `Group: Watchlist: famous5` → Universe ID: `group:<id>`
- `Group: Basket: momentum-basket` → Universe ID: `basket:<id>` (can still be implemented as a group kind; “basket” is about metadata)
- `Holdings view: high conviction` → Universe ID: `holdings_view:<id>`
- `Portfolio: basket-2025-01` → Universe ID: `portfolio:<id>`

Universe provides:
- `symbols[]` with optional `exchange`, `notes`, `target_weight` (depending on universe type)
- A “universe header” metadata (title, description, kind, counts)

#### 3.2 Overlays (optional enrichments)
Overlays decorate each symbol row with extra fields. Most overlays are keyed by `(symbol, exchange?)`.

Common overlays:
- **Holdings overlay** (only if the symbol is in Zerodha holdings): qty, avg price, invested, P&L%, today P&L%, etc.
- **Market overlay**: LTP, OHLCV history, chart sparkline, indicators.
- **Group membership overlay**: which groups include this symbol.
- **Basket overlay**: reference price at basket creation, basket qty, “since creation” P&L, weights, etc.

#### 3.3 Capabilities / constraints
Actions depend on what we know and what the broker allows.

Examples:
- BUY always possible (subject to broker rules and instrument availability).
- SELL:
  - Allowed even if symbol not held (MIS short), but the UI should clearly label product implications.
  - For holdings, SELL can optionally clamp qty to holdings qty for CNC; for MIS short this differs (needs explicit choice).
- `% of position` sizing only makes sense when “position value” exists (requires holdings qty and a usable price).
- Basket/portfolio sizing may have their own baseline values.

UniverseGrid should expose these capabilities clearly so users are never surprised.

---

## 4) Proposed UX / IA (“Universe picker” + “one grid”)

### 4.1 Navigation
Replace separate “holdings vs groups” mental model with a consistent “Universe” model:

- Sidebar:
  - Universes
    - Holdings (Zerodha)
    - Portfolios
      - <portfolio 1>
      - <portfolio 2>
    - Groups
      - Watchlists
        - <watchlist A>
        - <watchlist B>
      - Baskets
        - <basket X>
      - Holdings views
        - <holdings view Y>

This can be implemented incrementally:
- Phase 1: Add a Universe picker on the Holdings page header (dropdown).
- Phase 2: Promote it into the sidebar.

### 4.2 Single grid behavior
The grid stays the same everywhere:
- Column chooser + filters + density + export
- Selection (checkboxes)
- Bulk actions (buy/sell, create group, later: bulk alerts)
- Per-row actions (buy, sell, alert)

### 4.3 Column availability: “hide by default” rather than “not present”
To avoid fragmentation:
- Columns like Avg Price/Invested are **available**, but show `—` when the holdings overlay is absent.
- For watchlists/baskets, default column visibility hides holdings-only columns, but users can enable them.

This yields maximum reuse with minimal confusion.

---

## 5) Wireframes (ASCII)

### 5.1 “UniverseGrid” page

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Universe: [ Holdings (Zerodha) ▼ ]   [ Screener ] [ View settings ] [ Refresh ] │
│                                                                              │
│ Toolbar: Columns | Filters | Density | Export | Search...                    │
│ Actions: [ Bulk Buy ] [ Bulk Sell ] [ Create Group ] [ Bulk Alerts (later) ] │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ ] Symbol | Groups | Chart | Qty | Avg | LTP | RSI | ... | Alerts | Actions │
│ [ ] ...                                                                      │
│ [ ] ...                                                                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Universe picker (expanded)
```
Universe ▼
  Holdings (Zerodha)
  Portfolios
    Portfolio: basket-2025-01
  Groups
    Watchlists
      famous5
      momentum
    Baskets
      momentum-basket
    Holdings views
      high-conviction
```

### 5.3 Bulk trade dialog (same across universes)
```
Bulk buy/sell from <UniverseName>
  Position sizing: (Qty) (Amount) (% of position)
  Qty: "1,1,1,1,1"   [Manage]
  Amount: "17027.35" [Manage]  [x] Redistribute unused budget
  % of position: "..." [Manage]
  Order type: MARKET/LIMIT/SL/SL-M
  Price: per-holding list [Set prices] (disabled for MARKET/SL-M)
  Product: CNC/MIS
  Bracket/GTT options...
  [Create orders]
```

---

## 6) Concrete refactoring plan (detailed)

This is written as a “here → there” migration plan, so you can implement safely without breaking the app.

### Phase 0: Define the target interfaces (no UI changes)
Create types/interfaces and a small “adapter layer” without changing current behavior.

**Add new frontend module:**
- `frontend/src/universe/types.ts`

Suggested types:
- `UniverseId = string`
- `UniverseKind = 'HOLDINGS' | 'WATCHLIST' | 'BASKET' | 'PORTFOLIO' | 'HOLDINGS_VIEW'`
- `UniverseDefinition` (id, kind, label, description)
- `UniverseSymbol` (symbol, exchange?, notes?, target_weight?, meta?)
- `UniverseRow` (symbol, exchange, overlays)
- `UniverseCapabilities` (supportsHoldingsOverlay, supportsPctOfPosition, supportsTargetWeights, supportsShortSell, etc.)

**Goal:** create a stable “contract” so you can move logic out of `HoldingsPage.tsx`.

### Phase 1: Extract the grid component (still only for Holdings)
Create:
- `frontend/src/components/UniverseGrid/UniverseGrid.tsx`
- `frontend/src/components/UniverseGrid/useUniverseGridColumns.ts` (column definitions)
- `frontend/src/components/UniverseGrid/useUniverseSelectionActions.ts` (bulk buy/sell, create group)

Start by moving existing logic from `HoldingsPage.tsx` into the new component with minimal changes.

`HoldingsPage.tsx` becomes:
- fetch holdings
- compute `UniverseRows`
- render `<UniverseGrid rows=... universe=... overlays=... />`

**Acceptance criteria:**
- Holdings page looks/behaves the same.
- Bulk buy/sell and alert buttons still work.

### Phase 2: Introduce “Universe Picker” on Holdings page header
Add a dropdown at the top (like “View: Default/Risk”, but for universe selection).

Implement universes:
- `Holdings (Zerodha)` (existing)
- `Group: <name>` (pull group members and show them in the grid)

This will require:
- `listGroups()` (already exists)
- `fetchGroup(groupId)` or `listGroupMembers(groupId)` (already exists)

**Row composition logic:**
- For a group universe, rows = group members symbols.
- Join holdings overlay by symbol to populate qty/avg price/pnl when available.
- Show `—` for holdings-only metrics when not held.

### Phase 3: Make the bulk tooling universe-aware
Move the trade dialog into a reusable component:
- `frontend/src/components/Trade/BulkTradeDialog.tsx`
- `frontend/src/components/Trade/tradeSizing.ts` (shared sizing + allocation logic)

Key: the trade dialog should consume:
- `selectedRows[]` (symbols + overlays)
- `capabilities` (e.g., supportsPctOfPosition only when overlay exists)

**Rule set:**
- BUY always available.
- SELL always available (MIS short). If user selects CNC, SELL should behave as “sell holdings only” (clamp to holdings qty). If user selects MIS, allow short and do not clamp (but still validate non-negative).
- `% of position` only enabled when positionValue is computable for the row(s).

### Phase 4: Baskets + Portfolios (data model + overlays)
This phase is backend-heavy and should be planned carefully.

#### 4.1 Basket metadata model (recommended)
Even if you represent basket as a group kind, you’ll need per-member metadata beyond target_weight:
- `basket_qty`
- `basket_reference_price`
- `basket_created_at`

Options:
1) Extend GroupMember model to support basket fields (only for kind=BASKET).
2) Create a separate Basket/BasketMember model.

Because you already have groups and group members, Option (1) is often the faster path, but Option (2) is cleaner.

#### 4.2 Portfolio model
Portfolio is an instance of a basket, with a “buy reference price” and ideally a relationship to actual holdings.
If portfolios should always map to holdings, you can implement as:
- a group kind `PORTFOLIO` with members and reference prices, plus optional mapping to broker holdings.

UniverseGrid can then:
- use holdings overlay for live P&L
- use portfolio reference price for “since inception” P&L

### Phase 5: Alerts and screener across universes (alignment)
You already want:
- Alerts global per symbol.
- Ability to apply indicator/strategy to a universe (group) via screener or bulk action.

Recommended approach:
- Alerts remain global objects: `(symbol, exchange, rule, action?)`.
- Universe-level operations are just “bulk create alerts for selected symbols”.

This avoids contextual alerts and duplication.

---

## 7) Impact analysis (areas to assess up front)

### Frontend
- `HoldingsPage.tsx`: will shrink drastically; becomes a “Universe route” wrapper.
- `GroupsPage.tsx`: will either embed UniverseGrid for a selected group or become a “group editor” page plus “open in grid”.
- Shared components:
  - Grid columns
  - Selection model persistence (optional)
  - Bulk dialogs (buy/sell now; alerts later)
  - Screener integration: should apply to the current universe symbol list, not just holdings.

### Backend
- Groups API might need:
  - “universe endpoint” to return group members + metadata in one call.
  - Basket/portfolio member metadata fields if we implement them.
- Alerts/strategies remain global, but add endpoints for bulk creation/assignment if needed.

### Data semantics
- “Holdings-only metrics” should become optional overlay fields everywhere.
- “Short sell” with MIS should be supported in universes where symbol isn’t held.
- “% of position” should be disabled or show per-row eligibility, not silently compute nonsense.

### Performance
UniverseGrid will be used widely; it must be efficient:
- Batch-fetch market history/indicators in background (you already do this).
- Consider caching: LTP/indicator fetch by symbol across universes.
- Avoid O(n^2) joins; use maps keyed by symbol.

### Testing
- Backend: API validations for order creation already exist and are extended.
- Frontend: consider adding component tests for sizing/allocation logic (Vitest) once the logic is extracted into pure functions.

---

## 8) Recommendations / improvements to your idea

### 8.1 Make “Portfolio” a first-class universe, not just a group kind
Even if stored as a group, treat it as a distinct universe kind because:
- It has “since inception” P&L semantics.
- It wants portfolio-level analytics (equity curve, beta, etc.).

### 8.2 Keep “Group editor” separate from “UniverseGrid”
UniverseGrid is for *analysis + action*.
Group editor is for *membership/weights/notes management*.

You can link them:
- “Open in grid”
- “Edit members”

### 8.3 Don’t hide columns permanently; hide by default
Let watchlists optionally show “Holdings overlay columns” if the symbol is held, because that is often useful and creates the “aha” moment:
“My watchlist includes holdings; I can see both”.

---

## 9) Next step proposal

If you want to proceed with implementation, the lowest-risk first move is:
1) Create `UniverseGrid` component by extracting from `HoldingsPage.tsx` (Phase 1).
2) Add a simple Universe picker to switch between Holdings and a selected Group (Phase 2).

This will prove the architecture with minimal backend work and immediately unlock reuse across holdings and groups.
