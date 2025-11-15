# SigmaTrader – Implementation Report

This document tracks what has been implemented for each sprint/group/task in the SigmaTrader project, with a focus on code structure, APIs, tests, and any notable deviations or pending work.

---

## Sprint S01 – Project setup & scaffolding

### S01 / G01 – Backend scaffolding and FastAPI project setup

Tasks: `S01_G01_TB001`, `S01_G01_TB002`, `S01_G01_TB003`

- Chosen layout: `backend/` with `app/`, `tests/`, and config modules (instead of `src/app`).
  - `backend/app/main.py` – creates the FastAPI app, wires settings and routers.
  - `backend/app/api/routes.py` – root `/` endpoint and `/health` endpoint.
  - `backend/app/core/config.py` – `Settings` via `pydantic.BaseSettings`, using `ST_` env prefix and `.env` support; exposes app name, environment, version, debug, DB config.
- Basic endpoints:
  - `GET /` – returns JSON with a simple “SigmaTrader API is running” message and environment.
  - `GET /health` – returns `{ "status": "ok", "service": "SigmaTrader API", "environment": "<env>" }`.
- Backend dependencies:
  - `backend/requirements.txt` – FastAPI, Uvicorn, SQLAlchemy, Pydantic, Alembic, python-dotenv, pytest, httpx, plus tooling later.
- Tests:
  - `backend/tests/test_health.py` – verifies `/` and `/health` return 200 and expected payload fields.
- Docs:
  - `README.md` updated with backend setup instructions:
    - Create venv, install requirements, run `uvicorn app.main:app --reload --port 8000`.
    - Run backend tests with `pytest`.

Pending work (high-level):

- Add more structured error handling and logging for system endpoints if needed later.

---

### S01 / G02 – Frontend scaffolding and React/TypeScript/MUI setup

Tasks: `S01_G02_TF001`, `S01_G02_TF002`, `S01_G02_TF003`

- Frontend scaffold:
  - Created Vite React+TS app under `frontend/` using `npm create vite@latest frontend -- --template react-ts`.
  - Core dependencies: `react`, `react-dom`, `react-router-dom`, `@mui/material`, `@mui/icons-material`, `@emotion/react`, `@emotion/styled`.
- Layout and routing:
  - `frontend/src/main.tsx` – wraps app with `BrowserRouter`, MUI `ThemeProvider`, and `CssBaseline`.
  - `frontend/src/theme.tsx` – dark theme with primary/success/error colors.
  - `frontend/src/App.tsx` – renders `MainLayout` with nested `AppRoutes`.
  - `frontend/src/layouts/MainLayout.tsx` – MUI AppBar + permanent Drawer sidebar:
    - Navigation items: Dashboard (`/`), Queue (`/queue`), Orders (`/orders`), Analytics (`/analytics`), Settings (`/settings`).
    - Top-right chip showing API status.
  - `frontend/src/routes/AppRoutes.tsx` – defines route components.
  - `frontend/src/views/*Page.tsx` – placeholder views for Dashboard, Queue, Orders, Analytics, Settings.
- Health-check integration:
  - `frontend/src/services/health.ts` – `useHealth` hook:
    - Calls `/health` (relative) on mount and optionally polls every 15s.
    - Tracks status `idle|loading|ok|error` plus last payload and error.
  - `MainLayout` shows an API status chip (`API: Connected` / `API: Error` / `API: Checking`) based on `useHealth`.
  - `frontend/vite.config.ts` – dev proxy for `/health` to `http://localhost:8000`.
- Tests:
  - `frontend/vitest.config.ts` / `vitest.setup.ts` – JS DOM environment with Testing Library.
  - `frontend/src/App.test.tsx` – smoke test:
    - Renders `App` with router and theme.
    - Asserts presence of navigation labels and API status chip text.
- Docs:
  - `README.md` updated with frontend setup:
    - `cd frontend && npm install && npm run dev`.
    - `npm test` for Vitest.

Pending work (high-level):

- Refine tests to avoid `act(...)` warnings and cover more UI behaviors once real data is wired into Dashboard/Queue/Orders/Analytics.

---

### S01 / G03 – Tooling, Git workflow, and initial documentation

Tasks: `S01_G03_TB001`, `S01_G03_TF002`, `S01_G03_TB003`

- Backend tooling:
  - `backend/pyproject.toml` – config for:
    - Black (line length 88, target Python 3.10).
    - isort (Black profile, `app` as first-party).
    - Ruff (`lint.select = ["E","F","B"]`) for style/errors/bugbear; imports handled by isort.
  - `backend/requirements.txt` – added `black`, `isort`, `ruff`, `pre-commit`.
  - `.pre-commit-config.yaml` – hooks:
    - Black, isort, Ruff (`--fix`) scoped to `backend/`.
  - Codebase formatted and linted; Ruff config updated to the new `lint` section to remove deprecation warnings.
- Frontend tooling:
  - `eslint.config.js` – flat config using:
    - `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `eslint-config-prettier`.
  - `frontend/package.json`:
    - Scripts: `lint`, `format` (Prettier), `test`.
    - Dev deps: `eslint-config-prettier`, `prettier`, Testing Library, Vitest, jsdom.
  - Prettier config: `frontend/.prettierrc` with single quotes, no semicolons, trailing commas, width 88.
- Initial documentation:
  - `README.md` now describes:
    - How to run backend/frontend.
    - How to run tests.
    - How to run lint/format/pre-commit.
- Repo hygiene:
  - `.gitignore` – Python caches, venvs, node_modules, dist/build, SQLite DBs, editor files, etc.

Pending work (high-level):

- Optionally tighten Ruff/ESLint rules and introduce CI checks once a CI pipeline is set up.

---

## Sprint S02 – Core DB & domain model

### S02 / G01 – Design core SQLite schema

Tasks: `S02_G01_TB001`, `S02_G01_TB002`

- Schema design captured in `docs/db_schema_s02_v1.md`:
  - Tables:
    - `strategies` – execution mode, enabled flag, timestamps.
    - `risk_settings` – global vs per-strategy scope, limits, symbol lists, clamp/reject mode.
    - `alerts` – normalized TradingView alerts + raw payload.
    - `orders` – full order lifecycle, mapping to alerts/strategies, mode (AUTO/MANUAL), simulated flag.
    - `positions` – net positions by symbol/product.
    - `analytics_trades` – closed trades linking entry/exit orders and P&L metrics.
  - Constraints & indexes:
    - `CHECK` constraints for enums (execution mode, status, scope, clamp mode).
    - Foreign keys between strategies/alerts/orders/risk_settings.
    - Indexes for common queries (strategy+time, symbol+time, status, broker order id).
- Alignment notes:
  - Manual queue modeled via orders with `status=WAITING` and `mode=MANUAL`.
  - AUTO vs MANUAL captured both in `strategies.execution_mode` and `orders.mode`.
  - Risk settings support both global and per-strategy via `scope` and `strategy_id`.
  - Simulation planned via `orders.simulated`.

Pending work:

- Extend schema if needed for users, global settings, and advanced logging once those features are scoped.

---

### S02 / G02 – ORM models and migrations

Tasks: `S02_G02_TB001`, `S02_G02_TB002`, `S02_G02_TB003`

- ORM & DB session:
  - `backend/app/db/base.py` – SQLAlchemy `DeclarativeBase`.
  - `backend/app/db/session.py`:
    - `engine` configured from `Settings.database_url` (SQLite by default).
    - `SessionLocal` session factory (no autocommit/autoflush, `expire_on_commit=False`).
    - `get_db()` FastAPI dependency yielding a `Session`.
- ORM models: `backend/app/models/trading.py`
  - `Strategy`, `RiskSettings`, `Alert`, `Order`, `Position`, `AnalyticsTrade` mapped per schema doc with relationships & constraints.
  - Time fields now use timezone-aware UTC (`datetime.now(UTC)` via lambdas).
- Alembic:
  - `backend/alembic.ini` and `backend/alembic/env.py`:
    - `env.py` adjusts `sys.path` so `import app` works and uses `get_settings().database_url`.
    - `target_metadata = Base.metadata` for autogeneration.
  - Initial migration `backend/alembic/versions/0001_create_core_tables.py`:
    - Creates all core tables and indexes.
    - `alembic upgrade head` sets up `sigma_trader.db`.
- Tests:
  - `backend/tests/test_db_models.py` – smoke test:
    - Creates tables, persists a `Strategy`, and re-fetches it.

Pending work:

- Add future migrations as the schema evolves and ensure downgrade paths are maintained.

---

### S02 / G03 – Strategy & risk admin APIs + read-only UI

Tasks: `S02_G03_TB001`, `S02_G03_TB002`, `S02_G03_TF003`

- Backend schemas:
  - `backend/app/schemas/strategies.py` – `StrategyCreate/Update/Read`.
  - `backend/app/schemas/risk_settings.py` – `RiskSettingsCreate/Update/Read`, `RiskScope`, plus a validator enforcing scope vs strategy_id rules.
- Strategy APIs (`/api/strategies` – `backend/app/api/strategies.py`):
  - `GET /api/strategies/` – list all strategies.
  - `POST /api/strategies/` – create new strategy (400 on duplicate name).
  - `GET /api/strategies/{id}` – fetch by id.
  - `PUT /api/strategies/{id}` – update selected fields.
- Risk settings APIs (`/api/risk-settings` – `backend/app/api/risk_settings.py`):
  - `GET /api/risk-settings/` – list, filtered by optional `scope` and `strategy_id`.
  - `POST /api/risk-settings/` – create; enforces uniqueness on `(scope, strategy_id)`.
  - `GET /api/risk-settings/{id}` – fetch by id.
  - `PUT /api/risk-settings/{id}` – update with uniqueness check when scope/strategy_id change.
- Backend tests:
  - `backend/tests/test_strategies_api.py` – create strategy via API, list and confirm.
  - `backend/tests/test_risk_settings_api.py` –:
    - Resets schema in `setup_module`.
    - Creates a strategy, then GLOBAL and per-strategy risk settings via API.
    - Verifies filtering via scope/strategy_id.
- Frontend admin UI (Settings page):
  - `frontend/vite.config.ts` – proxy `/api` to `http://localhost:8000` in dev.
  - `frontend/src/services/admin.ts` – fetch helpers:
    - `fetchStrategies()` → `GET /api/strategies/`.
    - `fetchRiskSettings()` → `GET /api/risk-settings/`.
  - `frontend/src/views/SettingsPage.tsx`:
    - Loads strategies and risk settings on mount.
    - Shows loading spinner, error message, or two MUI tables:
      - Strategies: Name / Mode / Enabled / Description.
      - Risk Settings: Scope / Strategy ID / Max Order Value / Max Qty / Max Daily Loss / Clamp Mode.
    - Notes that this is a read-only view for now.

Pending work:

- Add DELETE endpoints, richer validation messages, and editable admin UI once full flows are designed.

---

## Sprint S03 – Webhook & manual queue backend (phase 1)

### S03 / G01 – TradingView webhook endpoint and alert validation

Tasks: `S03_G01_TB001`, `S03_G01_TB002`, `S03_G01_TB003`

- Config & schema:
  - `Settings.tradingview_webhook_secret` for validating incoming alerts.
  - `backend/app/schemas/webhook.py` – `TradingViewWebhookPayload` + `TradeDetails` to model the incoming JSON (secret, platform, strategy_name, symbol, exchange, interval, trade_details, optional bar_time).
- Endpoint:
  - `backend/app/api/webhook.py` – `POST /webhook/tradingview`:
    - Checks `payload.secret` against `Settings.tradingview_webhook_secret` (if set); invalid → 401 with error.
    - Resolves `Strategy` by `strategy_name` (if exists).
    - Creates and commits an `Alert` row with normalized fields and raw payload JSON.
    - Returns `{"id": alert_id, "status": "accepted"}` (later extended in S03/G02).
  - `backend/app/api/routes.py` includes `webhook.router` under `/webhook`.
- Tests:
  - `backend/tests/test_webhook_tradingview.py`:
    - `setup_module` sets `ST_TRADINGVIEW_WEBHOOK_SECRET`, clears and recreates tables.
    - `test_webhook_rejects_invalid_secret` – ensures 401 for wrong secret.
    - `test_webhook_persists_alert_with_valid_secret` – (later extended) verifies Alert creation and fields.

Pending work:

- Expand payload fields and validation once the final TradingView alert format and strategy routing rules are finalized.

---

### S03 / G02 – Alert→Order transformation and WAITING orders

Tasks: `S03_G02_TB001`, `S03_G02_TB002`, `S03_G02_TB003`

- Service:
  - `backend/app/services/orders.py` – `create_order_from_alert(db, alert, mode="MANUAL")`:
    - Maps an `Alert` into an `Order` with:
      - `alert_id`, `strategy_id`, `symbol`, `exchange`, `side`, `qty`, `price`.
      - `order_type="MARKET"`, `product="MIS"`, `gtt=False`.
      - `status="WAITING"`, `mode="MANUAL"`, `simulated=False`.
    - Persists and returns the `Order`.
- Webhook integration:
  - In `POST /webhook/tradingview`:
    - After saving the `Alert`, calls `create_order_from_alert`.
    - Response now includes:
      - `id` (alias for `alert_id`),
      - `alert_id`,
      - `order_id`,
      - `status: "accepted"`.
- Tests:
  - `backend/tests/test_webhook_tradingview.py::test_webhook_persists_alert_with_valid_secret` extended:
    - Asserts response contains `alert_id` and `order_id`.
    - Queries DB for both `Alert` and `Order`:
      - `Order.alert_id == alert_id`, symbol and side match the alert.
      - `Order.qty == alert.qty`.
      - `Order.status == "WAITING"`, `Order.mode == "MANUAL"`.

Pending work:

- Introduce strategy-aware defaults (e.g., per-strategy product/order_type), risk checks, and eventual connection to manual queue APIs and UI (planned for Sprint S04).

---

### S03 / G03 – Manual queue APIs and minimal order status updates

Tasks: `S03_G03_TB001`, `S03_G03_TB002`, `S03_G03_TB003`

- Queue and order listing APIs:
  - `backend/app/schemas/orders.py`:
    - `AllowedOrderStatus` – union of supported status strings.
    - `OrderRead` – Pydantic schema for serializing `Order` rows (id, alert_id, strategy_id, symbol, side, qty, price, order_type, product, gtt, status, mode, simulated, timestamps).
    - `OrderStatusUpdate` – minimal input schema with `status` limited to `"WAITING"` or `"CANCELLED"`.
  - `backend/app/api/orders.py`:
    - `GET /api/orders/queue`:
      - Returns manual queue orders only: filters `status="WAITING"`, `mode="MANUAL"`, `simulated=False`.
      - Optional `strategy_id` query parameter to narrow the queue.
      - Orders ordered by `created_at` for stable display.
    - `GET /api/orders/{order_id}`:
      - Returns a single order or 404 if not found.
    - `PATCH /api/orders/{order_id}/status`:
      - Minimal status update endpoint for queue scenarios.
      - Only allows transitions when the current status is in `{"WAITING", "CANCELLED"}`.
      - Target status is currently limited to `"WAITING"` or `"CANCELLED"` (captured by `OrderStatusUpdate`).
      - Returns the updated order after commit.
  - `backend/app/api/routes.py`:
    - Includes the orders router under `prefix="/api/orders", tags=["orders"]`.

- Tests:
  - `backend/tests/test_orders_api.py`:
    - `setup_module`:
      - Sets a dedicated `ST_TRADINGVIEW_WEBHOOK_SECRET`.
      - Drops and recreates tables for a clean start.
    - Helper `_create_order_via_webhook()`:
      - Posts a TradingView payload to `/webhook/tradingview`, returning the `order_id` from the response.
    - `test_queue_listing_and_cancel_flow`:
      - Creates a `WAITING` order via webhook.
      - Confirms `GET /api/orders/queue` contains the new order id.
      - Calls `PATCH /api/orders/{id}/status` with `{"status":"CANCELLED"}`.
      - Confirms the returned order has status `CANCELLED`.
      - Verifies `GET /api/orders/queue` no longer lists that order.
      - Asserts in the DB that `order.status == "CANCELLED"`.

- Validation & regression:
  - All backend tests now pass (`pytest`): 8 tests including DB models, health, strategies, risk settings, webhook, and orders API.

Pending work:

- Introduce richer queue operations (e.g., explicit “execute” transitions, editing qty/price before execution) and integrate these APIs into the frontend Queue and Orders pages in Sprint S04.
- Add further validation around allowed status transitions as more states are used in later sprints.

This report will continue to evolve as new sprints and groups are implemented. For each new slice, we will add a short summary of:

- Code structure and key files.
- APIs and behaviors.
- Tests and how to run them.
- Deviations from the original plan.
- Pending work to revisit later.**

---

## Sprint S04 – Manual queue frontend & basic orders UI

### S04 / G01 – Dashboard layout and navigation structure

Tasks: `S04_G01_TF001`, `S04_G01_TF002`

- Navigation:
  - Top-level navigation (Dashboard, Queue, Orders, Analytics, Settings) and sidebar layout were already implemented in Sprint S01 / G02 via `MainLayout` and routing, so these tasks are considered implemented with that work.
- Dashboard:
  - Dashboard page currently shows a simple heading and placeholder text; widgets for P&L, trade count, and connection status will be fleshed out once analytics and broker integration are in place.

Pending work:

- Add actual P&L/trade count widgets and connection health summaries on the Dashboard once we have S05–S07 data and broker connectivity.

---

### S04 / G02 – Waiting queue UI for manual orders

Tasks: `S04_G02_TF001`, `S04_G02_TF002`, `S04_G02_TF003`, `S04_G02_TB004`

- Backend support (started in S03, extended here):
  - `backend/app/api/orders.py`:
    - `GET /api/orders/queue` – lists manual queue orders (WAITING/MANUAL, non-simulated) with optional `strategy_id` filter.
    - `PATCH /api/orders/{id}/status` – minimal status updates between `WAITING` and `CANCELLED` for manual queue flows.
- Frontend Queue UI:
  - `frontend/src/services/orders.ts`:
    - `fetchQueueOrders(strategyId?)` – calls `/api/orders/queue`.
    - `cancelOrder(orderId)` – `PATCH /api/orders/{id}/status` with `{status: "CANCELLED"}`.
  - `frontend/src/views/QueuePage.tsx`:
    - Loads queue orders on mount, showing:
      - Created At (localized datetime).
      - Symbol, Side, Qty, Price, Status.
      - A `Cancel` button per row.
    - Shows loading spinner while fetching and an error message on failure.
    - On cancel:
      - Calls `cancelOrder`.
      - Removes the order from the in-memory queue on success.
      - Displays error if the cancel call fails.
    - Inline editing and “Execute” actions are intentionally deferred to later sprints.
- Tests:
  - `frontend/src/QueuePage.test.tsx`:
    - Mocks `fetch` to return a sample queue with a single order.
    - Renders `QueuePage` with router/theme.
    - Asserts that “Waiting Queue” renders and that the mocked symbol (e.g., `NSE:TCS`) appears once data is loaded.

Pending work:

- Add inline editing for qty/price/order_type/product and an “Execute” action wired into future backend endpoints.
- Enhance queue filtering and sorting once real workflows are exercised.

---

### S04 / G03 – Basic order history UI and backend API

Tasks: `S04_G03_TB001`, `S04_G03_TF002`

- Backend orders history:
  - `backend/app/api/orders.py`:
    - `GET /api/orders/`:
      - Returns orders ordered by `created_at` descending.
      - Optional filters:
        - `status` – filter by a single status string.
        - `strategy_id` – filter by strategy.
      - Intended as a simple history API; more filters (symbol, date range) can be added later.
- Frontend Orders history UI:
  - `frontend/src/services/orders.ts`:
    - `fetchOrdersHistory({ status?, strategyId? })` – wrapper around `GET /api/orders/`.
  - `frontend/src/views/OrdersPage.tsx`:
    - Loads order history on mount.
    - Shows:
      - Created At, Symbol, Side, Qty, Price, Status, Mode.
    - Displays loading spinner and error message similar to the queue page.
    - Shows a friendly “No orders yet” message when the list is empty.
    - Filtering controls are not yet exposed in the UI; this page currently uses the default unfiltered history.

Pending work:

- Add filter controls (date range, strategy, status, symbol) to the Orders page UI.
- Extend the backend `/api/orders/` endpoint with richer filters (e.g., date range, simulation flag) as needed by the UI.
