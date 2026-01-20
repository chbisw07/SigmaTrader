# SigmaQLab/SigmaTrader — Groups Redesign (Executive Summary)

This note summarizes what exists today vs what must change for the redesign PRD, and the safest implementation order.

Authoritative PRD: `docs/groups_watchlists_baskets_portfolios_redesign_prd.md`  
Detailed gap analysis: `docs/groups_redesign_gap_analysis.md`

## What Exists Today
- A single “Groups” page (`frontend/src/views/GroupsPage.tsx`) that can create/edit groups and members across kinds: `WATCHLIST`, `MODEL_PORTFOLIO` (basket), `PORTFOLIO`, plus legacy `HOLDINGS_VIEW`.
- Groups are persisted as `groups` + `group_members` (`backend/app/models/groups.py`) with member fields: `target_weight`, `notes`, `reference_qty`, `reference_price`.
- A watchlist import + dynamic dataset system exists (`/api/groups/import/watchlist`, `group_imports`, `group_import_values`) and is wired into the Groups page.
- Portfolios have partial execution semantics:
  - Orders can be attributed to a portfolio via `orders.portfolio_group_id`.
  - Executed order sync updates `GroupMember.reference_qty` and weighted-average `reference_price` for that portfolio (`backend/app/services/portfolio_allocations.py`).
  - The UI has “allocation health” and “reconcile allocations” tooling for portfolio groups.
- Live LTP exists only via broker-specific endpoints (`/api/zerodha/ltp`, `/api/angelone/ltp`) and holdings snapshots; there is no generic/bulk market quotes endpoint for watchlists/baskets.

## What Must Change (PRD-Driven)
- Watchlists: implement fast symbol add (paste + shortcuts) and remove Notes; add live LTP/day% columns.
- Baskets: introduce a real basket builder (funds + allocation mode + locks + validation) and persist frozen prices + frozen timestamp.
- Allocation logic: extract to a tested pure function (shared across basket builder, buy preview, future rebalance).
- Buy flow: implement “Buy basket → portfolio” that creates a portfolio linked to the basket and snapshots the frozen prices used.
- Data model/API: add basket config + freeze persistence and portfolio/basket linkage fields (current schema has no `frozen_at`, no `frozen_price`, no basket→portfolio reference).

## Safest Order To Implement
1) Define + implement a bulk quotes/LTP contract (backend + frontend polling hook).
2) Build the allocation engine (pure + tested) for Weight mode + locks first.
3) Add basket config + freeze snapshot persistence (schema + APIs).
4) Refactor Groups UI into reusable components (reduce risk), then implement Watchlist fast-add + LTP columns.
5) Implement BasketBuilderDialog (Weight MVP) + Freeze.
6) Implement BuyPreviewDialog + basket→portfolio creation + order attribution; then extend to Amount/Qty modes and portfolio auditing fields.

## Implementation Plan (S32 Tasks)
- Spreadsheet source of truth: `docs/sprint_tasks_codex.xlsx` (Sprint `S32`, Groups `G01`/`G02`/`G03`)
- Markdown mirror: `docs/sprint_tasks_groups_redesign.md`
- Strict sequencing: `G01 Watchlist` → `G02 Basket` → `G03 Portfolio` (each is a vertical slice before moving on)

## Feature Flag (Non-Negotiable)
- Flag name: `FEATURE_GROUPS_REDESIGN`
- Rollout approach (to avoid big-bang refactor): the same flag is “expanded” kind-by-kind:
  - Phase 1: when enabled, only `WATCHLIST` uses redesigned components; baskets/portfolios remain legacy.
  - Phase 2: baskets join the redesigned path; portfolios remain legacy.
  - Phase 3: portfolios join; legacy path remains available when the flag is off.

## Assumptions (Explicit)
- Live Watchlist/Basket pricing uses a new poll-friendly bulk quotes endpoint (vs per-symbol broker LTP calls), with caching/throttling to avoid rate-limit issues.
- Paste-add “skip duplicates + invalid” requires either a new API behavior or a new endpoint; legacy endpoints remain unchanged for existing callers.
- “Buy timestamp” in Portfolio can be stored as the time the buy flow is initiated (order creation time); executed fills continue to be the source of truth for qty/avg via existing order sync.

## Blockers / Operational Notes
- `docs/~$sprint_tasks_codex.xlsx` indicates the Excel file may be open in another process; this can cause save conflicts in some environments. The update to `docs/sprint_tasks_codex.xlsx` succeeded in this run.
