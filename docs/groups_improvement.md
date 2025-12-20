# Groups Improvement – CSV/XLSX Import With Dynamic Columns (Watchlists + Portfolios)

This document captures the discussion (“QA”) and a recommended design plan for importing TradingView (or other) `.csv` / `.xlsx` files into SigmaTrader Groups (watchlists now; portfolios next), while preserving SigmaTrader’s own canonical columns and adding **dynamic, per-import columns** that appear only for the groups that use them.

---

## 1) What you want (restated)

### Watchlist import
- Upload a `.csv`/`.xlsx` exported from TradingView (or other).
- During import:
  - choose the file’s **Symbol column** (and optionally **Exchange** column if present),
  - choose which **other columns** to import as dynamic columns.
- Create a new **Group (Watchlist)** whose members are the imported symbols.
- The selected dynamic columns become part of that group’s display on Holdings/Groups “Open in grid” view.
- Another group should not show these extra columns unless it was created/imported with them.

### Portfolio import (later)
- Same as watchlist import + additionally map file columns into SigmaTrader’s internal portfolio fields (minimum: `buy_date`, `avg_buy_price`, `qty`, `weight`).
- Still keep dynamic columns for extra metadata (rating, sector, strategy tag, etc.).

---

## 2) Feasibility & impact (expert view)

### Is it a good idea?
Yes—this is a strong, “product-y” feature:
- TradingView watchlists/portfolios become first-class citizens inside SigmaTrader.
- You gain “research metadata overlays” (e.g., score, sector, tags) without bloating your core schema.
- It keeps Holdings UI flexible: groups can behave like “custom universes with custom columns”.

### Complexity level
Medium-to-high, but manageable if we enforce a clean boundary:
- **Core Group membership** stays simple (symbol+exchange).
- **Dynamic columns** live in a separate “import dataset” layer, referenced by group.
- UI rendering becomes dynamic but is straightforward with MUI `DataGrid` column generation.

### Biggest risks
- Symbol matching errors (TradingView formats vary).
- Data hygiene: inconsistent types, blank values, duplicate columns, duplicate symbols.
- Long-term maintainability if we try to support “everything” on day-1.

Recommended approach: implement watchlist import first (CSV), then extend to XLSX and portfolio mapping.

---

## 3) Recommended mental model (keep it generic)

### A. Group remains a list of members
Canonical membership key:
- `(exchange, symbol)` (uppercased, normalized)

### B. Import creates a “Dataset”
Each import produces:
- a dataset schema: list of dynamic columns (name + type + formatting),
- per-member values: `{ (exchange,symbol) -> { colKey -> value } }`

### C. A group can reference one dataset (initially)
The group points to the dataset it was created from.
Later, we can support merging multiple datasets, but it’s not needed initially and complicates UX.

---

## 4) Data model proposal (backend)

### 4.1 New tables (suggested)

**`group_imports`**
- `id`
- `group_id`
- `source` (e.g., `TRADINGVIEW`, `CUSTOM`)
- `original_filename`
- `file_hash` (optional)
- `created_at`
- `schema_json` (list of dynamic column definitions)
- `symbol_mapping_json` (what column mapped to symbol/exchange; normalization rules)

**`group_import_values`**
- `id`
- `import_id`
- `symbol` (canonical)
- `exchange` (canonical)
- `values_json` (map of `colKey -> scalar`)

This keeps dynamic columns **fully attached to the import**.

Alternative: EAV table (`import_id`, `symbol`, `exchange`, `colKey`, `value`) is more queryable but heavier. JSON is simpler and consistent with how SigmaTrader already stores some dynamic structures.

### 4.2 Column definition contract (in `schema_json`)
Each column should have:
- `key` (stable, machine-safe identifier; derived from header)
- `label` (what we show in UI)
- `type`: `string | number | percent | date | datetime | boolean`
- formatting hints:
  - decimals, percent scaling, currency, etc.
- `source_header` (original file column name for traceability)

### 4.3 Where does this surface in the app?
- Groups page “Open in grid” and Holdings page “View: <group>”:
  - Base columns (SigmaTrader’s existing holdings columns),
  - plus dataset dynamic columns (only if selected group has an import dataset).

---

## 5) Import UX (front-end)

### Step 1: Upload file
- Accept `.csv` first (robust + easy).
- Add `.xlsx` later (more parsing complexity).

### Step 1.5: Broker symbol validation (mandatory)
During preview/mapping (before creating the group), SigmaTrader should validate that every imported member resolves to a **known broker instrument** for the chosen exchange (`NSE`/`BSE`):
- Normalize the candidate symbol (strip `NSE:` prefixes, trim, uppercase, optional “special char cleanup” per rules).
- Resolve against the broker’s instrument master (Kite instruments / local cache).
- If a symbol **cannot be resolved**, it is **not imported** and the UI should show a clear, actionable message (e.g., “`FOO` not found on `NSE`; skipping”).

Expectation: this should “never happen” for clean TradingView exports, but we still enforce it to avoid creating broken groups that don’t work with candles/alerts/orders.

### Step 2: Preview + column discovery
Show:
- detected headers
- a preview of first N rows
- inferred types (editable)

### Step 3: Mapping
**Required mapping**
- “Which column is Symbol?”
- Optional: “Which column is Exchange?”
  - If missing: default exchange = `NSE` (configurable)

**Import columns selection**
- Checkbox list of file columns (excluding Symbol/Exchange) to import as dynamic columns.
- Allow renaming labels (optional).

### Import column restrictions (no OHLCV/derived metrics)
Imported columns should be restricted to **metadata-like fields** (safe to carry as annotations), and SigmaTrader should **refuse** importing anything that looks like:
- raw price/volume fields (e.g., `close`, `price`, `ltp`, `volume`, `ohlc`, `open/high/low`)
- performance/return fields (e.g., `return`, `ret`, `pnl`, `p&l`, `%`, `change`, `drawdown`)
- indicators/metrics derived from OHLCV (e.g., `rsi`, `sma`, `ema`, `atr`, `macd`, `beta`, etc.)

Rationale:
- These values are either already computed inside SigmaTrader from the candle store, or can become stale/inconsistent if imported from external sources.
- It avoids users “over-trusting” external derived metrics that don’t match SigmaTrader’s internal candles/timeframes.

UX behavior:
- If the user selects a disallowed column, show a polite explanation (e.g., “Price/volume/indicator fields are not importable; SigmaTrader computes these internally from candles.”) and **do not import** the field.
- The UI can pre-tag columns as “Allowed / Not allowed” using header heuristics, but the backend must enforce the rule as well.

### Step 4: Normalization rules (important)
Allow toggles:
- strip `NSE:` prefix (`NSE:ACUTAAS` → `ACUTAAS`)
- strip special chars (`GVT&D` vs `GVTD`) (should be consistent with positions logic)
- trim whitespace
- uppercase

### Step 5: Create group
- name + group kind (watchlist)
- “overwrite existing group” vs “create new”
- results:
  - group created
  - members imported
  - dataset stored + attached

---

## 6) Holdings page behavior (dynamic columns)

When a group is selected:
- if the group has no dataset: show normal holdings columns only.
- if the group has a dataset:
  - add those dataset columns to the grid.

### Column ordering strategy
Keep it predictable:
1) Identity: Symbol, Exchange
2) Core SigmaTrader columns (price, pnl, etc.)
3) Dynamic imported columns (in the user-selected order)

### Filtering/sorting
Dynamic columns should be sortable/filterable (DataGrid supports this if we provide the `type` correctly).

---

## 7) Portfolio import (phase-2)

Portfolio import is “watchlist import + mapping into internal fields”.

### Minimum required portfolio mappings
- `qty`
- `avg_buy_price`
- `buy_date`
- `target_weight` (optional but recommended)

### Storage strategy
Use group member fields for portfolio-specific attributes:
- either extend `group_members` with dedicated fields (qty, avg_buy, buy_date, weight)
- or store in a portfolio-specific table keyed by `(group_id, exchange, symbol)` to avoid polluting generic watchlists.

I recommend a dedicated table for portfolio fields to keep the generic watchlist clean.

---

## 8) Implementation plan (suggested)

### Phase 1 — Watchlist CSV import + dynamic columns
1. Backend:
   - add import tables and migration
   - add `POST /api/groups/import` endpoint:
     - accepts parsed rows + mapping instructions (or raw file upload; see open questions)
     - creates group + import dataset + values
   - add `GET /api/groups/{id}/grid` response shape that merges:
     - base member list + dynamic columns schema + values
2. Frontend:
   - import dialog on Groups page:
     - upload → preview → mapping → pick columns → create
   - Holdings page:
     - when viewing group: fetch dataset schema + values and create DataGrid columns dynamically

### Phase 2 — XLSX support
Two options:
- client-side parse (SheetJS): fast UX, but adds bundle size and parsing differences across browsers.
- server-side parse (Python): consistent, but adds dependency + resource handling.

Recommendation: ship CSV first, then add XLSX after the watchlist flow is stable.

### Phase 3 — Portfolio mode
1. Add portfolio-specific group kind
2. Add required mapping UI + validation
3. Persist portfolio fields and show them in the grid (and later analytics)

---

## 9) Open questions (need your answers)

1) Should imports be stored as:
   - **raw file** (for audit/re-import) or
   - only parsed structured data (schema + values)?

2) Should a group support:
   - exactly **one** dataset (simple), or
   - multiple datasets merged (complex; needs collision/precedence rules)?

3) Symbol identity rules:
   - Do you want a single canonical format (e.g. `EXCH:SYMBOL` everywhere), or always `(exchange, symbol)` separately?
   - How should we handle a file that contains the same symbol on multiple exchanges?

4) Column naming:
   - If the CSV contains duplicate headers (or headers that clash with SigmaTrader base columns), what should the conflict behavior be?

5) Update semantics:
   - When you re-import the same file (or a newer export), do you want:
     - replace dataset + values, or
     - create a new dataset version (history)?

---

## 10) Your answers + impact analysis

This section captures your answers to the open questions, and how they influence the design.

### Q1) Store raw file vs parsed data
**Your answer:** You will keep the source file wherever you want; SigmaTrader should persist the imported symbols + selected column values in DB as long as the watchlist exists.

**Impact / recommendation:**
- This maps cleanly to “store structured data only” (schema + values) and **do not store the raw file** inside SigmaTrader.
- We should still store minimal metadata for traceability: `original_filename`, `imported_at`, optional `source_hint` (TradingView), and maybe an optional `user_note`.
- Tradeoff:
  - Pros: simpler storage, fewer security concerns, no filesystem coupling.
  - Cons: cannot “re-parse” later if we improve normalization heuristics; but you can always re-import manually.

### Q2) One dataset per group vs multiple datasets
**Your answer:** Single dataset per group; during import we should detect override risk and offer “override/erase” vs “do not override”.

**Impact / recommendation:**
- We keep **one dataset per group** (simple and robust).
- “Override risk” needs to be explicitly defined:
  - creating a new group with same name (name collision)
  - importing into an existing group (replace vs merge members)
  - importing dynamic columns where column keys/labels overlap (replace column values vs skip)
- Recommended import modes (UI choice):
  - **Replace dataset** (clear prior dynamic columns + values, write new)
  - **Merge dataset** (keep existing columns; add new columns; for overlapping columns choose overwrite/skip)
  - **Replace members** (drop group members not present in new file) vs **Merge members** (add/update only)

### Q3) Symbol identity rules (ISIN-centric identity)
**Your answer (key idea):**
- Internally maintain identity via `(isin, nse_code, bse_code, symbol_name)` and present symbols as `NSE:HCL` style.
- Broker symbols should map to this via `(isin, …, broker_symbol)`.
- “Other symbols” (TradingView, etc.) should map to the same ISIN-backed identity.

**Impact / feasibility (honest):**
- This is a **very good long-term architecture** for Indian equities because:
  - it de-duplicates symbol naming differences across sources,
  - it avoids edge cases like special characters (`GVT&D`) and symbol renames,
  - it allows clean mapping between `NSE`/`BSE` codes and broker-specific `tradingsymbol`.
- However, adopting ISIN as the primary identity is **larger scope** than just “import watchlist CSV” because it touches:
  - instruments storage (we need an `instruments` table that includes ISIN and per-exchange codes),
  - group membership keys (today likely `(exchange,symbol)`),
  - candles linkage (should ideally be keyed by instrument identity, not free-text symbols),
  - holdings/positions merging and symbol normalization across the app.

**Practical phased approach (recommended):**
1) **Phase 1 (watchlist CSV import)**: treat **broker instruments as the source of truth now**:
   - “Other sources symbol” → must resolve to a broker instrument for `NSE/BSE` (mandatory).
   - Keep canonical group member key as `(exchange, symbol)` (broker-resolved), and store a stable broker reference (e.g., `instrument_token`; plus `isin` if present in the broker instrument master).
2) **Phase 1.5 (instrument master)**: introduce/extend an internal `instruments` registry that stores `isin`, `nse_code`, `bse_code`, `name`, and broker identifiers; group members reference this instrument row.
3) **Phase 2 (wider refactor)**: gradually migrate existing places to use the instrument registry for identity (groups/holdings/screener/alerts/dashboards/candles).

**Important constraint baked into this doc (already):**
- Imports must match broker symbols for NSE/BSE; non-resolvable rows are rejected/skipped. This naturally pushes us toward the instrument-master approach.

### Q4) Duplicate headers / header conflicts
**Your answer:** The mapping + column selection UI can handle duplicates; the user can choose which one to import.

**Impact / recommendation:**
- Good: we treat “duplicate headers” as selectable candidates.
- We still need stable internal keys:
  - if two selected columns have the same label/header, we should generate distinct `key`s (e.g., `sector`, `sector__2`) and show a UI hint.
- We also enforce the “no OHLCV/derived metrics” restriction at this stage.

### Q5) Re-import / update semantics
**Your answer:** Offer the user an option to keep older dataset or replace dataset + values.

**Impact / recommendation:**
- For v1, implement:
  - **Replace**: delete/overwrite the dataset schema + values for that group, then import fresh.
  - **Keep existing**: cancel import or import as a **new group** (recommended UX, avoids silent divergence).
- Optional “history” can be added later by versioning datasets (not required in your answer).
