# SigmaTrader – Groups, Baskets & Universe (Phase‑1 Design)

---

## 1. Scope and goals (Phase‑1)

This document describes a **Phase‑1** design for:

1. A **Holdings screener** (covered in more detail in `stock_screener.md`).  
2. **Groups / baskets / basic watchlists**, built on top of the existing holdings + indicator infrastructure.  
3. A minimal notion of a **stock universe**, sufficient to support groups and future fundamentals work.

The focus is on what we can implement *now* without needing a full fundamentals ingest pipeline or deep AI integration.

---

## 2. Concepts and data model

### 2.1 Symbols & universe (minimal view)

We treat **symbol + exchange** as the primary identifier, consistent with the rest of SigmaTrader:

- `instrument` (already exists via Zerodha instruments / market_data):
  - `symbol`, `exchange`, `instrument_token`, `name`, `tick_size`, `lot_size`, etc.

For Phase‑1 we do **not** add heavy fundamentals here. We only need enough metadata to:

- Attach symbols to groups and screeners.  
- Display them cleanly in grids and dialogs.  
- Later, join to fundamentals snapshots when that project lands.

### 2.2 Groups / baskets / watchlists

We introduce two core tables:

1. `groups`
   - `id` (PK)  
   - `user_id`  
   - `name` (e.g. “Momentum basket”, “Dividend watchlist”)  
   - `kind` (enum):
     - `WATCHLIST` – arbitrary set of symbols the user wants to follow.  
     - `MODEL_PORTFOLIO` – a target portfolio (may or may not match actual holdings).  
     - `HOLDINGS_VIEW` – group defined in the context of the current holdings only (optional).  
   - `description` (optional)  
   - `created_at`, `updated_at`

2. `group_members`
   - `id` (PK)  
   - `group_id` (FK → `groups.id`)  
   - `symbol`  
   - `exchange`  
   - `target_weight` (nullable, decimal fraction; if null, members are equal‑weight)  
   - `notes` (optional)  
   - `created_at`, `updated_at`

Key properties:

- A symbol can be in multiple groups.  
- Groups are user‑scoped; different users can have their own baskets.  
- `target_weight` allows both equal‑weight and custom allocations.

---

## 3. Groups UI & workflows

### 3.1 Groups page (new)

Add a new **“Groups”** or **“Baskets”** section under Settings or as its own nav item later.

Features:

- **Groups list**:
  - DataGrid with columns: `Name`, `Kind`, `# Members`, `Description`, `Created`, `Updated`.  
  - Actions: **Edit**, **Duplicate**, **Delete** (soft delete), plus **Create group** button.

- **Group editor**:
  - Top section:
    - Name, Kind, Description.  
  - Members section:
    - DataGrid with columns: `Symbol`, `Exchange`, `Target weight %`, `Notes`.  
    - Row‑level actions: Add, Remove, Edit weight/notes.  
    - “Equalise weights” button to set all members to equal weight.  
    - “Normalise weights” button to rescale weights to sum to 100%.

### 3.2 Integrating groups into Holdings

We reuse the Holdings DataGrid to show how groups apply to *actual* positions:

- **New columns**:
  - `Cluster` (already present from correlation analytics).  
  - `Group(s)` – short list of group names or a primary group tag (e.g. first group or a chip count).

- **Interactions**:
  - From a holdings row:
    - “Assign to group…” action opens a small dialog listing existing groups with checkboxes.  
    - Optional quick shortcut: “Create new group with selected holdings”.
  - Filter:
    - Use the DataGrid column filter to show holdings belonging to a specific group.

This links *real positions* to *model portfolios* and watchlists without duplicating data.

---

## 4. Using groups in trading flows

### 4.1 Equal‑amount allocation into a group (legacy; removed)

Goal: “I have ₹X and I want to allocate it equally across the stocks in Group G, using my existing Buy flows and risk controls.”

Note: The legacy **"Allocate funds"** dialog in Groups has been removed. For creating queued orders from a set of symbols, use a Basket + the "Buy basket → portfolio (preview)" flow.

Flow:

1. User selects a group G (typically a Basket) and uses the "Buy basket → portfolio (preview)" flow.
2. A dialog asks:
   - `Total amount` to allocate.  
   - Allocation mode:
     - `Equal weight` – each member gets `X / N`.  
     - `Target weights` – each member gets `X * target_weight_i`.  
   - Other common order settings:
     - Side = BUY.  
     - Order type = MARKET / LIMIT.  
     - Product = CNC / MIS.  
     - Optional: apply **bracket re‑entry GTT** defaults.
3. SigmaTrader computes per‑symbol qty:
   - For each member, use last price and round down to whole shares.  
   - Discard or reallocate any small residual cash.
4. The backend:
   - Creates one **WAITING** manual order per symbol through the existing manual‑queue API.  
   - Applies existing risk checks.
5. User reviews and executes from the Queue when ready.

This workflow leverages:

- Existing **order sizing** (we’re just generating many orders at once).  
- Existing **bracket orders** and risk controls.  
- The new groups/shared allocation logic is mostly front‑end and some helper maths.

### 4.2 Applying alerts/strategies to a group

We can reuse the indicator alerts infrastructure:

1. User selects a group G.  
2. Clicks **“Attach strategy…”** and chooses a strategy template (e.g. ST004‑G PVT bullish correction).  
3. Backend:
   - For each member symbol, creates an `indicator_rule` linked to that strategy with:
     - Universe/scope = the symbol.  
     - DSL or simple builder settings copied from the template.
4. Alerts appear in:
   - The Alerts page (with `cluster/group` columns later).  
   - The Holdings `Alerts` column as per existing behaviour.

This gives you “strategy per basket” without changing the alert engine itself.

---

## 5. Screener interplay (Phase‑1)

The **Holdings screener** from `stock_screener.md` remains focused on the current holdings but can be enhanced by groups:

- Screener expressions can reference:
  - Group membership (e.g. “Group == Momentum” in builder mode or `IN_GROUP('Momentum')` in DSL).  
  - Risk/indicator metrics we already compute.

- Screeners can be saved alongside groups, e.g.:
  - “Group A, but only oversold names with RSI < 30 and 1M PnL% < -10%”.

Batch actions from the screener can target:

- Selected holdings in a particular group.  
- New group creation from screener results (e.g. “Create group from screened rows”).

---

## 6. Future‑phase universe and fundamentals (outline only)

Not in Phase‑1, but influenced by this design:

- Add a `fundamentals_snapshot` table keyed by `(as_of_date, symbol, exchange)` with selected metrics.  
- Support CSV/Excel imports from screener.in / TV into this snapshot table.  
- Let groups and screeners filter by fundamentals (e.g. `ROE > 15 AND DebtEquity < 0.5`) in addition to technicals.  
- Once these metrics are reliable, tie into Tarkash for RAG‑style Q&A and strategy suggestions.

The important point: groups and the holdings screener are designed to work *even before* fundamentals arrive, and will only get more powerful as the universe grows.

