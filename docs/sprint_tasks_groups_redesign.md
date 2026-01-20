# Sprint Tasks - Groups Redesign (S32)

Authoritative PRD: `docs/groups_watchlists_baskets_portfolios_redesign_prd.md`
Gap analysis: `docs/groups_redesign_gap_analysis.md`
Exec summary: `docs/qlab_impl_report.md`

Feature flag: `FEATURE_GROUPS_REDESIGN` (legacy Groups remains available until Phase 3 is complete; within S32 this flag is expanded kind-by-kind).

## Sprint
- Sprint ID: `S32`
- Groups: `G01` Watchlist, `G02` Basket, `G03` Portfolio
- Task sizing: each task is targeted at ~1-3 hours (recorded in the `remarks` column in `docs/sprint_tasks_codex.xlsx`).

## G01 - Watchlist redesign (flagged, end-to-end; no basket/portfolio deps)

| Task ID | Task | Status | Notes (Est/Paths/Deps) |
|---|---|---|---|
| `S32_G01_TF001` | Frontend: Introduce `FEATURE_GROUPS_REDESIGN` flag plumbing; when enabled, apply redesign ONLY for WATCHLIST groups; keep legacy behavior for other kinds. | implemented | Est: 2h \| Area: FE \| Paths: frontend/src/views/GroupsPage.tsx, frontend/src/config/features.ts (new) \| Deps: None |
| `S32_G01_TB001` | Backend: Add batch symbol normalizer/validator endpoint for paste workflows (supports NSE:/BSE: prefixes, trims, resolves against Listings) returning valid + invalid with reasons. | implemented | Est: 3h \| Area: BE \| Paths: backend/app/api/market_data.py (or new market_symbols router), backend/app/schemas/market_data.py (or new schema), backend/app/models/listings.py (existing Listing model) \| Deps: None |
| `S32_G01_TB002` | Backend: Add bulk add members (skip duplicates/invalid) API for watchlists so paste-add can be one request and always returns per-symbol results (no hard-fail on first duplicate). | implemented | Est: 3h \| Area: BE \| Paths: backend/app/api/groups.py, backend/app/schemas/groups.py \| Deps: S32_G01_TB001 |
| `S32_G01_TB003` | Backend: Add bulk quotes endpoint (LTP + optional prev_close/day%) with safe throttling/caching for watchlists (poll-friendly). | implemented | Est: 3h \| Area: BE \| Paths: backend/app/api/market_data.py, backend/app/services/market_quotes.py (new) \| Deps: None |
| `S32_G01_TT001` | Tests: Backend unit tests for bulk quotes endpoint (stub broker client; verify shape, caching behavior boundaries, and error handling). | implemented | Est: 2h \| Area: TEST/QA \| Paths: backend/tests/test_market_quotes.py (new) \| Deps: S32_G01_TB003 |
| `S32_G01_TF002` | Frontend: Build `SymbolQuickAdd` component (autocomplete via `/api/market/symbols`, paste parsing comma/newline, NSE:/BSE: prefixes, dedupe, invalid feedback, `/` focus + Enter add). | implemented | Est: 3h \| Area: FE \| Paths: frontend/src/components/groups/SymbolQuickAdd.tsx (new), frontend/src/components/groups/symbolParsing.ts (new) \| Deps: S32_G01_TF001, S32_G01_TB001, S32_G01_TB002 |
| `S32_G01_TF003` | Frontend: Add quotes polling hook/service for watchlist rows (batch requests, throttle, only poll visible symbols). | implemented | Est: 3h \| Area: FE \| Paths: frontend/src/services/marketQuotes.ts (new), frontend/src/hooks/useMarketQuotes.ts (new) \| Deps: S32_G01_TB003 |
| `S32_G01_TF004` | Frontend: Implement redesigned Watchlist members grid (remove Notes for WATCHLIST only; add LTP + optional Day%) and wire into `GroupsPage` behind flag; preserve legacy grid for other kinds; keep Import untouched. | implemented | Est: 3h \| Area: FE \| Paths: frontend/src/views/GroupsPage.tsx, frontend/src/components/groups/WatchlistMembersGrid.tsx (new) \| Deps: S32_G01_TF001, S32_G01_TF002, S32_G01_TF003 |
| `S32_G01_TT002` | Tests: Frontend unit tests for SymbolQuickAdd parsing/dedupe + basic UX (paste add 30-50 symbols stays responsive). | implemented | Est: 2h \| Area: TEST/QA \| Paths: frontend/src/components/groups/symbolParsing.test.ts (new), frontend/src/components/groups/SymbolQuickAdd.test.tsx (new) \| Deps: S32_G01_TF002 |
| `S32_G01_TD001` | Docs/QA: Add a short manual QA checklist for Watchlist redesign (create, bulk paste, LTP visible, no regressions in groups list; confirm Import unchanged). | implemented | Est: 1h \| Area: DOCS \| Paths: docs/qa/groups_watchlist_redesign.md (new) \| Deps: S32_G01_TF004 |

## G02 - Basket redesign (flagged, end-to-end; NO execution)

| Task ID | Task | Status | Notes (Est/Paths/Deps) |
|---|---|---|---|
| `S32_G02_TF001` | Frontend: Implement allocation engine (pure functions) (Weight mode only) with lock semantics + actions (Equalize, Normalize unlocked, Clear) and validation outputs. | planned | Est: 3h \| Area: FE \| Paths: frontend/src/groups/allocation/engine.ts (new), frontend/src/groups/allocation/types.ts (new) \| Deps: S32_G01_TF001 |
| `S32_G02_TT001` | Tests: Unit tests for allocation engine (lock math, rounding, validation, actions). | planned | Est: 2h \| Area: TEST/QA \| Paths: frontend/src/groups/allocation/engine.test.ts (new) \| Deps: S32_G02_TF001 |
| `S32_G02_TB001` | Backend (MIGRATION): Extend group/basket persistence for baskets: funds, allocation_mode, frozen_at; per-member frozen_price + lock flag + weight input storage; keep Import flows unchanged. | planned | Est: 3h \| Area: BE/MIGRATION \| Paths: backend/alembic/versions/00xx_add_basket_fields.py (new), backend/app/models/groups.py, backend/app/schemas/groups.py \| Deps: None |
| `S32_G02_TB002` | Backend: Add basket APIs: update basket config (funds/mode), freeze prices endpoint (sets frozen_at + per-member frozen_price), and basket read response includes frozen + live (via quotes endpoint). | planned | Est: 3h \| Area: BE \| Paths: backend/app/api/groups.py, backend/app/services/baskets.py (new) \| Deps: S32_G02_TB001, S32_G01_TB003 |
| `S32_G02_TT002` | Tests: Backend tests for basket freeze/persistence APIs (freeze overwrite behavior, frozen_price stored per member, frozen_at stored). | planned | Est: 2h \| Area: TEST/QA \| Paths: backend/tests/test_baskets_freeze.py (new) \| Deps: S32_G02_TB002 |
| `S32_G02_TF002` | Frontend: Implement `BasketBuilderDialog` (Weight mode only) using allocation engine + quotes hook; includes lock toggles, frozen vs live columns, and freeze button. | planned | Est: 3h \| Area: FE \| Paths: frontend/src/components/groups/BasketBuilderDialog.tsx (new), frontend/src/components/groups/MembersGrid.tsx (new or extracted), frontend/src/services/groups.ts \| Deps: S32_G02_TF001, S32_G01_TF003, S32_G02_TB002 |
| `S32_G02_TF003` | Frontend: Wire Basket edit flow into `GroupsPage` for `MODEL_PORTFOLIO` behind `FEATURE_GROUPS_REDESIGN`; ensure legacy Allocate flow still exists and remains unchanged when flag off. | planned | Est: 2h \| Area: FE \| Paths: frontend/src/views/GroupsPage.tsx \| Deps: S32_G02_TF002 |
| `S32_G02_TF004` | Frontend: Basket summary + validation (fresh cost now, remaining cash/overbudget, validation errors); persist weights/locks/funds; enforce sum(weights)=100% to be valid in Weight mode. | planned | Est: 3h \| Area: FE \| Paths: frontend/src/components/groups/BasketBuilderDialog.tsx, frontend/src/groups/allocation/engine.ts \| Deps: S32_G02_TF003 |
| `S32_G02_TD001` | Docs/QA: Add basket QA checklist + behavior notes (Weight mode only; freeze semantics; no execution). | planned | Est: 1h \| Area: DOCS \| Paths: docs/qa/groups_basket_redesign.md (new) \| Deps: S32_G02_TF004 |

## G03 - Portfolio buy flow (flagged, end-to-end; basket->portfolio)

| Task ID | Task | Status | Notes (Est/Paths/Deps) |
|---|---|---|---|
| `S32_G03_TB001` | Backend (MIGRATION): Add portfolio origin + snapshot persistence (portfolio references basket_id; copy frozen snapshot for traceability; store buy timestamp). | planned | Est: 3h \| Area: BE/MIGRATION \| Paths: backend/alembic/versions/00xx_add_portfolio_origin_snapshot.py (new), backend/app/models/groups.py (or new model), backend/app/schemas/groups.py (or new schema) \| Deps: S32_G02_TB001 |
| `S32_G03_TB002` | Backend: Implement Buy endpoint (accept basket_id + planned orders; create PORTFOLIO group; copy members + frozen snapshot; create queued orders attributed via `orders.portfolio_group_id`; keep risk policy untouched). | planned | Est: 3h \| Area: BE \| Paths: backend/app/api/groups.py (or new buy router), backend/app/services/buy_basket.py (new), backend/app/api/orders.py (existing order creation) \| Deps: S32_G03_TB001, S32_G02_TB002 |
| `S32_G03_TT001` | Tests: Backend tests for Buy endpoint (portfolio created, linkage to basket, snapshot stored, orders created with portfolio_group_id). | planned | Est: 2h \| Area: TEST/QA \| Paths: backend/tests/test_buy_basket.py (new) \| Deps: S32_G03_TB002 |
| `S32_G03_TF001` | Frontend: Implement `BuyPreviewDialog` for baskets (planned qty per symbol, est cost now, product + order type; optional safety buffer); uses allocation engine + quotes hook. | planned | Est: 3h \| Area: FE \| Paths: frontend/src/components/groups/BuyPreviewDialog.tsx (new), frontend/src/groups/allocation/engine.ts \| Deps: S32_G02_TF001, S32_G01_TF003 |
| `S32_G03_TF002` | Frontend: Wire "Buy basket" action into `GroupsPage` for baskets behind feature flag; call buy endpoint; on success navigate to the new portfolio (select in Groups or open in holdings grid). | planned | Est: 2h \| Area: FE \| Paths: frontend/src/views/GroupsPage.tsx, frontend/src/services/groups.ts (add buy API) \| Deps: S32_G03_TB002, S32_G03_TF001 |
| `S32_G03_TT002` | QA: Manual end-to-end checklist (buy basket->portfolio created; portfolio holdings update after execution/sync; basket remains reusable; legacy Groups unchanged when flag off). | planned | Est: 2h \| Area: TEST/QA \| Paths: docs/qa/groups_portfolio_buy_flow.md (new) \| Deps: S32_G03_TF002, S32_G03_TB002 |
| `S32_G03_TD001` | Docs: Update redesign rollout notes (feature flag behavior across phases; assumptions; known limitations). | planned | Est: 1h \| Area: DOCS \| Paths: docs/qlab_impl_report.md \| Deps: S32_G03_TF002 |

