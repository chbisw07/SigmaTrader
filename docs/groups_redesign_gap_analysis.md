# Groups Redesign (PRD → Current Implementation) Gap Analysis

Authoritative PRD: `docs/groups_watchlists_baskets_portfolios_redesign_prd.md`

Scope note (Step 1): Analysis + recommended implementation sequence only (no code changes, no sprint task edits).

---

## A) PRD Key Requirements (Checklist)

### Group Types + Lifecycle
- [ ] Support 3 user-facing group types: **Watchlist**, **Basket**, **Portfolio**
- [ ] Enforce lifecycle conceptually: `Watchlist → (optional) Basket → Buy → Portfolio`
- [ ] Separate **intent** (basket) from **execution** (portfolio)

### Groups Page Layout + Reusable Components
- [ ] Left **GroupListPanel**: tabs/filters (All/Watchlists/Baskets/Portfolios), search, sort (Updated/Name/Members), row actions (Edit/Duplicate/Export/Delete)
- [ ] Right panel context-aware header: name + type chip + metadata; type-specific primary actions
- [ ] Reusable components: `GroupListPanel`, `SymbolQuickAdd`, `MembersGrid`, `BasketBuilderDialog`, `BuyPreviewDialog`

### Watchlist UX (Critical)
- [ ] **SymbolQuickAdd**: autocomplete + NSE/BSE toggle
- [ ] Add flows: single symbol + Enter; paste comma/newline separated; accept `NSE:HDFCBANK` / `BSE:500180`
- [ ] Keyboard shortcuts: `/` focus input; `Enter` add; `Ctrl+V` bulk paste
- [ ] Skip duplicates/invalid with user feedback
- [ ] Watchlist columns: Symbol, Exchange, **LTP (live)**, Day% (optional), Actions; **remove Notes**

### Basket Builder + Allocation Engine (Critical)
- [ ] Basket stores funds + mode + symbol set + frozen reference prices (and shows live comparison)
- [ ] BasketBuilderDialog: funds, mode, price source (Live vs Frozen), freeze prices, totals + validation
- [ ] Allocation modes: Weight (default), Amount, Qty
- [ ] Lock semantics and actions: equalize, normalize unlocked, clear unlocked
- [ ] Allocation engine is a **single pure function**: inputs (funds/mode/symbols+LTP/locks/user inputs) → outputs (qty/amount/weight per row + totals + validation)

### Price Freezing
- [ ] Persist `frozen_at` (timestamp)
- [ ] Persist `frozen_price` per symbol; UI shows live vs frozen and % change

### Buy Basket → Portfolio
- [ ] Buy preview dialog (product/order type defaults; safety buffer optional)
- [ ] Buying creates a Portfolio that stores: executed qty, avg buy price, buy timestamp, reference basket id, frozen prices snapshot
- [ ] Basket remains reusable after buy

---

## B) Current Implementation Inventory

### Frontend (Current)
- `frontend/src/routes/AppRoutes.tsx` — route `"/groups"` → `GroupsPage`.
- `frontend/src/layouts/MainLayout.tsx` — left nav includes “Groups” linking to `"/groups"`.
- `frontend/src/views/GroupsPage.tsx` - **single, monolithic** implementation for:
  - Left groups list: MUI `DataGrid` with `Import` + `New` buttons; columns include name/kind/members/updated + edit/delete.
  - Right details: `Open in grid` navigates to `"/holdings?universe=group:<id>"`.
  - Member add UX: MUI `Autocomplete` backed by `searchMarketSymbols()`; separate Exchange select; includes a **Notes** input; supports "Bulk add" (multiline symbols + one exchange applied to all).
  - Member grid: always shows `Target weight` and **Notes**; for `MODEL_PORTFOLIO`/`PORTFOLIO` also shows `reference_qty` + `reference_price`; for `PORTFOLIO` adds allocation health chip and a "Reconcile portfolio allocations" dialog.
  - Legacy "Allocate funds to group members" dialog existed previously but has been removed.
- `frontend/src/services/groups.ts` — Types + API calls for Groups:
  - `GroupKind` includes `WATCHLIST`, `MODEL_PORTFOLIO`, `PORTFOLIO`, plus extra `HOLDINGS_VIEW` (not in PRD).
  - Calls `/api/groups/*` for CRUD, members, datasets, portfolio allocations + reconcile.
- `frontend/src/services/marketData.ts` — symbol search (`/api/market/symbols`) and OHLCV history (`/api/market/history`); **no LTP fetch** here.
- `frontend/src/services/brokerRuntime.ts`, `frontend/src/services/zerodha.ts`, `frontend/src/services/angelone.ts` — broker-specific `fetch*Ltp()` used elsewhere (e.g. `frontend/src/views/QueuePage.tsx`) but **not wired into Groups/watchlists**.
- `frontend/src/views/HoldingsPage.tsx` — includes “Group selected symbols” dialog that can create a Watchlist/Basket/Portfolio and (for Basket/Portfolio) seeds `reference_qty`/`reference_price` from holdings.
- `frontend/src/components/UniverseGrid/UniverseGrid.tsx` — reusable DataGrid wrapper with quick filter toolbar; Groups page currently uses `DataGrid` directly instead of this wrapper.

### Backend (Current)
- Models / DB schema:
  - `backend/app/models/groups.py` — `Group` and `GroupMember`.
    - `Group.kind` enum: `WATCHLIST`, `MODEL_PORTFOLIO`, `HOLDINGS_VIEW`, `PORTFOLIO`.
    - `GroupMember` fields: `symbol`, `exchange`, `target_weight` (0..1), `notes`, `reference_qty`, `reference_price`.
  - Migrations:
    - `backend/alembic/versions/0022_add_groups_and_members.py` — creates `groups` + `group_members`.
    - `backend/alembic/versions/0023_add_group_member_reference_fields.py` — adds `reference_qty`/`reference_price` + `PORTFOLIO` kind.
    - `backend/alembic/versions/0032_add_group_import_datasets.py` — creates `group_imports` + `group_import_values` (dynamic import columns).
    - `backend/alembic/versions/0042_add_orders_portfolio_group_id.py` — adds `orders.portfolio_group_id`.
  - Orders attribution / portfolio baseline updates:
    - `backend/app/api/orders.py` — `create_manual_order()` accepts optional `portfolio_group_id` (validated to be a `PORTFOLIO` group).
    - `backend/app/models/trading.py` — `Order` includes `portfolio_group_id`.
    - `backend/app/services/portfolio_allocations.py` — on executed fills, updates `GroupMember.reference_qty` and computes weighted-average `reference_price` (BUY) for that portfolio.
    - `backend/app/services/order_sync.py`, `backend/app/services/order_sync_angelone.py` — call `apply_portfolio_allocation_for_executed_order()` when orders transition to EXECUTED.
- Groups API:
  - `backend/app/api/groups.py`
    - `GET /api/groups/` list (optionally filtered by kind)
    - `POST /api/groups/` create
    - `GET /api/groups/{group_id}` detail (includes members)
    - `PATCH /api/groups/{group_id}` update
    - `DELETE /api/groups/{group_id}` delete
    - `GET /api/groups/{group_id}/members` list members
    - `POST /api/groups/{group_id}/members` add member
    - `POST /api/groups/{group_id}/members/bulk` bulk add
    - `PATCH /api/groups/{group_id}/members/{member_id}` update member
    - `DELETE /api/groups/{group_id}/members/{member_id}` delete member
    - `POST /api/groups/import/watchlist` CSV import to group + dataset (`backend/app/schemas/group_imports.py`)
    - `GET /api/groups/{group_id}/dataset` and `GET /api/groups/{group_id}/dataset/values` (dynamic import columns)
    - `GET /api/groups/allocations/portfolio` baselines across all portfolio groups for symbol+exchange
    - `POST /api/groups/allocations/portfolio/reconcile` reconcile per-symbol allocations vs broker holdings
    - `GET /api/groups/memberships/by-symbol` membership lookup (symbol → group names)
- Market data + pricing:
  - `backend/app/api/market_data.py` — `/api/market/symbols`, `/api/market/history`, `/api/market/status`; **no generic LTP endpoint**.
  - Broker LTP exists (auth required):
    - `backend/app/api/zerodha.py` — `GET /api/zerodha/ltp`
    - `backend/app/api/angelone.py` — `GET /api/angelone/ltp`

### Current API/JSON Contracts (Used by Groups Page)

Source of truth for FE contract expectations: `frontend/src/services/groups.ts`.

- `GET /api/groups/` → `Group[]`
  - `{ id, owner_id?, name, kind, description?, member_count, created_at, updated_at }`
- `GET /api/groups/{group_id}` → `GroupDetail`
  - Same as `Group` plus `members: GroupMember[]`
- `GroupMember`
  - `{ id, group_id, symbol, exchange?, target_weight?, reference_qty?, reference_price?, notes?, created_at, updated_at }`
- `POST /api/groups/` payload (create)
  - `{ name, kind?, description? }`
- `PATCH /api/groups/{group_id}` payload (update)
  - `{ name?, kind?, description? }`
- `POST /api/groups/{group_id}/members` payload (add member)
  - `{ symbol, exchange?, target_weight?, reference_qty?, reference_price?, notes? }`
- `PATCH /api/groups/{group_id}/members/{member_id}` payload (edit member)
  - `{ target_weight?, reference_qty?, reference_price?, notes? }`
- `POST /api/groups/import/watchlist` (import CSV) → `GroupImportWatchlistResponse`
  - `{ group_id, import_id, imported_members, imported_columns, skipped_symbols: [...], skipped_columns: [...], warnings: [...] }`
- `GET /api/groups/{group_id}/dataset` → `GroupImportDataset`
  - `{ id, group_id, source, original_filename?, created_at, updated_at, columns: [{key,label,type,source_header?}], symbol_mapping }`
- `GET /api/groups/{group_id}/dataset/values` → `{ items: GroupImportDatasetValuesItem[] }`
  - `GroupImportDatasetValuesItem = { symbol, exchange, values: { ...dynamic columns... } }`
- `GET /api/groups/allocations/portfolio` → `PortfolioAllocation[]`
  - `{ group_id, group_name, symbol, exchange, reference_qty?, reference_price? }`
- `POST /api/groups/allocations/portfolio/reconcile` → `{ symbol, exchange, holding_qty, allocated_total, updated_groups }`
- `GET /api/groups/memberships/by-symbol?symbols=...` → `{ memberships: Record<string, string[]> }`

Notes persistence (PRD deprecation target):
- Stored in `group_members.notes` (`backend/app/models/groups.py`) and shown in `frontend/src/views/GroupsPage.tsx`; PRD requires removing Notes from watchlists (field can remain for legacy/other uses, but should be hidden/ignored for watchlists).

### Candidate Persistence Locations for PRD Basket Fields (Design Choice)

PRD-required fields not present today: basket funds + mode + locks + frozen prices (`frozen_at`, `frozen_price` per symbol) and basket→portfolio linkage.

Two viable approaches:
- **A) Extend existing tables (lowest migration overhead)**:
  - Add basket fields on `groups` (e.g., `basket_funds`, `basket_mode`) and add basket state on `group_members` (e.g., `locked`, `frozen_price`, `frozen_at`, plus per-mode user input fields).
  - Tradeoff: `group_members` becomes a “union” of semantics across kinds; requires strict kind-scoping rules.
- **B) Add dedicated basket/portfolio metadata tables (cleaner long-term)**:
  - `basket_configs` keyed by `group_id` + `basket_member_state` keyed by `(group_id, symbol, exchange)` (or `group_member_id`) + optional `basket_snapshots` for versioned freezes.
  - Add `portfolio_origin` or `portfolio_runs` table to link portfolio groups to a basket + snapshot used at buy time.
  - Tradeoff: more schema/API work up front, but clearer semantics and easier versioning/auditing.

### Data Tables / Fields Relevant to Groups
- `groups`: `id`, `owner_id`, `name`, `kind`, `description`, `created_at`, `updated_at`
- `group_members`: `id`, `group_id`, `symbol`, `exchange`, `target_weight`, `notes`, `reference_qty`, `reference_price`, `created_at`, `updated_at`
- `group_imports`: `group_id`, `source`, `schema_json`, `symbol_mapping_json`, `created_at`, `updated_at`
- `group_import_values`: `import_id`, `symbol`, `exchange`, `values_json`, `created_at`
- `orders`: includes `portfolio_group_id` (used to update portfolio allocations on execution)

---

## C) Gap Analysis

| PRD Requirement | Current Status | Proposed Change (FE/BE) | Risk / Complexity Notes |
|---|---|---|---|
| 3 types: Watchlist/Basket/Portfolio | **Partial** (has `WATCHLIST`, `MODEL_PORTFOLIO`, `PORTFOLIO` + extra `HOLDINGS_VIEW`) | FE: align labels + filters to PRD; BE: decide whether `HOLDINGS_VIEW` stays hidden/legacy or becomes a separate feature outside redesign | Risk: other features (rebalance/backtests) may depend on `PORTFOLIO`/`HOLDINGS_VIEW` semantics |
| Lifecycle: Watchlist → Basket → Buy → Portfolio | **Missing** | FE: add explicit “Create basket from watchlist” and “Buy basket” flows; BE: add portfolio creation endpoint linking to basket | Needs product decision for naming/duplicate handling; impacts order attribution |
| GroupListPanel (tabs/filter/search/sort/actions) | **Partial** (DataGrid list; edit/delete only; no tabs/search/duplicate/export) | FE: introduce `GroupListPanel` and consolidate list behaviors; add export/duplicate; add kind tabs | Low/medium; mostly UI refactor but touches navigation/state |
| Context-aware right panel actions per type | **Partial** (`Open in grid` generic; portfolio-only reconcile tooling) | FE: type-specific actions and dialogs; align actions with PRD (watchlist: Open/Export; basket: Edit/Buy/Open; portfolio: Open/Rebalance/Add funds) | Medium; requires new dialogs + backend contracts |
| Watchlist SymbolQuickAdd (paste, shortcuts, NSE/BSE parsing) | **Missing** | FE: implement `SymbolQuickAdd` with paste parsing + keyboard shortcuts; keep `/api/market/symbols` for autocomplete | Medium; needs careful UX + dedupe/feedback behavior |
| Watchlist columns (Symbol/Exchange/LTP/Day%/Actions; remove Notes) | **Missing** | FE: remove Notes column for watchlists; add LTP + day% columns | Depends on solving LTP/day% source |
| Live LTP source for watchlist/basket | **Missing** (only holdings last_price; broker LTP exists but not bulk) | BE: add **bulk quote/LTP** endpoint (likely under `/api/market/*`) backed by canonical broker + caching; FE: polling hook for visible rows | Medium/high; careful with rate limits, auth, caching, fallbacks |
| BasketBuilderDialog (funds + mode + locks + totals + validation) | **Missing** (legacy "Allocate funds" was ad-hoc and not persistent) | FE: build dialog + `MembersGrid` mode-aware; BE: persist basket config + frozen prices + lock/user inputs | Medium/high; depends on allocation engine + schema |
| Allocation modes (Weight/Amount/Qty) + lock semantics | **Missing** | FE: allocation engine supports all modes; BE: persist per-member user inputs + lock flags | High; requires clear data model for mode/user inputs |
| Allocation engine as a pure function | **Missing** (logic embedded in `GroupsPage.tsx`) | FE: new `allocateBasket()` module + tests; use in basket builder and buy preview | Medium; correctness/rounding/edge cases are the main risk |
| Freeze prices: persist `frozen_at` + per-symbol `frozen_price` | **Missing** | BE: add fields/tables for frozen snapshot; FE: freeze action calls backend, shows deltas | Medium; design decision: revisioning vs overwrite |
| BuyPreviewDialog | **Missing** | FE: preview planned orders + cost; allow product/order type selection (default MARKET/CNC) | Medium; depends on allocation engine + LTP + backend buy endpoint |
| Buy basket creates Portfolio + links basket + stores snapshot | **Missing** (no basket→portfolio conversion) | BE: endpoint creates portfolio group + copies members + frozen snapshot + basket reference; FE: “Buy basket” flow | High; must define idempotency, naming, and partial/failed execution behavior |
| Portfolio stores executed qty + avg buy price + buy timestamp | **Partial** (`reference_qty`/`reference_price` update on executed orders; no timestamps) | BE: add per-member executed timestamps (or separate fills table); ensure order sync updates; FE: show cost basis clearly | Medium; schema change + backfill strategy needed |
| Remove Notes column from watchlists | **Missing** (Notes stored + used everywhere) | FE: hide Notes for watchlists; BE: keep field for legacy or migrate usage | Low; but requires migration plan if Notes exists in user data |

---

## D) Assumptions & Open Questions (Only Blockers)

1) **LTP source for Watchlist/Basket**: should this come from (a) a canonical broker connection (Zerodha/AngelOne), (b) a cached market-data service, or (c) “best available” (broker when connected, else last close)? PRD requires live LTP, but current `/api/market/*` does not expose LTP.

2) **Freeze versioning**: when users click “Freeze Prices Now”, do we overwrite the previous frozen snapshot, or create a versioned “basket revision” so old buys can always reference the exact snapshot used?

3) **Buy creates portfolio naming + multiplicity**: does each buy create a *new* portfolio every time (recommended by PRD mental model), or can it “buy into an existing portfolio”?

---

## E) Recommended Implementation Sequence (Dependencies Included)

1) **Lock down pricing contract (LTP/day%)**
   - BE: introduce a bulk quotes endpoint (e.g. `GET/POST /api/market/quotes`) that returns `{symbol, exchange, ltp, prev_close?, day_pct?}` using canonical broker LTP APIs with caching/throttling.
   - FE: add a polling hook usable by watchlists + baskets (poll only visible rows).

2) **Build the allocation engine first (pure + tested)**
   - FE: implement a pure `allocateBasket()` function (Weight mode first) including lock semantics + `equalize/normalize/clear` actions and validation.
   - This unblocks BasketBuilderDialog, BuyPreviewDialog, and future rebalance reuse.

3) **Define persistence for baskets and freeze snapshots**
   - BE schema: add basket config (funds, mode) and per-member fields for locks + user inputs + frozen_price (+ frozen_at at group or member level).
   - Add read/write APIs for basket config + freeze action.

4) **Refactor Groups UI into reusable components without behavior changes**
   - FE: extract `GroupListPanel` + `MembersGrid` scaffolding from `GroupsPage.tsx` to reduce risk before changing UX.

5) **Implement Watchlist fast-add UX + remove Notes from watchlists**
   - FE: replace current add-member row with `SymbolQuickAdd` (paste parsing + shortcuts); remove Notes column for watchlists; add LTP/day% columns using quotes hook.

6) **Implement BasketBuilderDialog (Weight mode MVP)**
   - FE: dialog UX with funds + weights + locks + freeze + totals; persist basket config + frozen prices.
   - Validate “must sum to 100% before buy” in Weight mode.

7) **Implement BuyPreviewDialog + Basket → Portfolio creation**
   - BE: create portfolio from basket (link + snapshot); FE: buy flow creates orders attributed to the new portfolio (`portfolio_group_id`) so execution updates qty/avg buy price.

8) **Extend to Amount/Qty modes + harden portfolio semantics**
   - FE: add Amount + Qty modes to allocation engine + dialog.
   - BE: add timestamps / revision linkage needed for “portfolio = executed basket” auditing.
