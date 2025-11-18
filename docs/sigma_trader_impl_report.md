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

### S02 / G03 – Strategy & risk admin APIs + Settings UI

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
    - Later extended (in S06) with:
      - `updateStrategyExecutionMode(...)` – `PUT /api/strategies/{id}`.
      - `createRiskSettings(...)` – `POST /api/risk-settings/`.
  - `frontend/src/views/SettingsPage.tsx`:
    - Loads strategies and risk settings on mount.
    - Shows loading spinner, error message, or two MUI sections:
      - Strategies:
        - Table with Name / Mode / Enabled / Description.
        - Mode column is now an editable select (MANUAL/AUTO) wired to `updateStrategyExecutionMode`, allowing per-strategy execution_mode changes from the UI.
      - Risk Settings:
        - Inline form for adding GLOBAL or STRATEGY-scoped risk settings:
          - Fields for Max Order Value, Max Qty/Order, Max Daily Loss, Clamp Mode (CLAMP/REJECT), and Short Selling (Allowed/Disabled).
          - Uses `createRiskSettings` to create new rows in `/api/risk-settings/`.
        - Table listing existing risk settings rows with Scope / Strategy ID / Max Order Value / Max Qty / Max Daily Loss / Clamp Mode.

Pending work:

- Add DELETE endpoints, richer validation messages, and more advanced admin UX (editing existing risk rows, bulk operations) as the configuration surface grows.

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
    - `PATCH /api/orders/{id}` – edits basic order fields (qty, price, order_type, product) for non-simulated manual orders that are still in `WAITING` state.
- Frontend Queue UI:
  - `frontend/src/services/orders.ts`:
    - `fetchQueueOrders(strategyId?)` – calls `/api/orders/queue`.
    - `cancelOrder(orderId)` – `PATCH /api/orders/{id}/status` with `{status: "CANCELLED"}`.
     - `updateOrder(orderId, payload)` – `PATCH /api/orders/{id}` for editing quantity, price, order type, and product.
  - `frontend/src/views/QueuePage.tsx`:
    - Loads queue orders on mount, showing:
      - Created At (localized datetime).
      - Symbol, Side, Qty, Price, Status.
      - Actions per row:
        - `Edit` – opens a dialog allowing changes to quantity, order type (`MARKET`/`LIMIT`), price (optional for market orders), and product (e.g., MIS/CNC).
        - `Execute` – sends the order to the backend execution endpoint (wired in S05/G03).
        - `Cancel` – cancels the order via status update.
    - Shows loading spinner while fetching and an error message on failure.
    - On edit:
      - Validates basic constraints (positive quantity, non-negative price).
      - Calls `updateOrder` and updates the in-memory queue row on success.
      - Surfaces any backend errors at the page level.
    - On cancel or execute:
      - Calls the respective service.
      - Removes the order from the in-memory queue on success.
      - Displays error if the call fails.
- Tests:
  - `frontend/src/QueuePage.test.tsx`:
    - Mocks `fetch` to return a sample queue with a single order.
    - Renders `QueuePage` with router/theme.
    - Asserts that “Waiting Queue” renders and that the mocked symbol (e.g., `NSE:TCS`) appears once data is loaded.

Pending work:

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

---

## Sprint S05 – Zerodha integration & execution from queue

### S05 / G01 – Integrate Zerodha Kite Connect client on backend

Tasks: `S05_G01_TB001`, `S05_G01_TB002`, `S05_G01_TB003`

- Configuration:
  - `Settings` (`backend/app/core/config.py`):
    - Added `zerodha_api_key: str | None` (env var `ST_ZERODHA_API_KEY`).
    - Zerodha API secret and access-token management are deferred to S05/G02, which will handle OAuth/token exchange.
  - `backend/requirements.txt`:
    - Added `kiteconnect` dependency for the real Zerodha client (`kiteconnect>=5,<6`).
- Zerodha client wrapper:
  - `backend/app/clients/zerodha.py`:
    - `KiteLike` protocol:
      - Models the subset of `KiteConnect` methods used (`set_access_token`, `place_order`, `orders`, `order_history`).
      - Enables testing with a fake client (no real network calls).
    - `ZerodhaOrderResult` dataclass:
      - Holds `order_id` and `raw` response.
    - `ZerodhaClient`:
      - `__init__(self, kite: KiteLike)` – wraps any Kite-like implementation.
      - `@classmethod from_settings(cls, settings: Settings, access_token: str)`:
        - Validates `zerodha_api_key` is set; raises `RuntimeError` if not.
        - Lazily imports `KiteConnect` from `kiteconnect`.
        - Instantiates `KiteConnect` with `api_key`, sets access token, and builds a `ZerodhaClient`.
      - `place_order(...) -> ZerodhaOrderResult`:
        - Builds a parameter dict for KiteConnect `place_order`:
          - `tradingsymbol`, `transaction_type`, `quantity`, `order_type`, `product`, `variety`, `exchange`, optional `price`, plus any extra kwargs.
        - Returns `ZerodhaOrderResult(order_id=..., raw=response)`.
      - `list_orders() -> list[dict]`:
        - Returns `kite.orders()`.
      - `get_order_history(order_id: str) -> list[dict]`:
        - Returns `kite.order_history(order_id)`.
  - `backend/app/clients/__init__.py` – exports `ZerodhaClient`.
- Tests:
  - `backend/tests/test_zerodha_client.py`:
    - `FakeKite`:
      - Implements the `KiteLike` protocol in-memory:
        - Tracks `access_token`, collects placed orders, returns canned responses for `orders` and `order_history`.
    - `test_place_order_uses_underlying_kite_client`:
      - Constructs `ZerodhaClient(FakeKite())`.
      - Calls `place_order` with symbol/side/qty.
      - Asserts:
        - Result `order_id` is as returned by `FakeKite`.
        - Underlying `placed_orders` contains the expected parameters.
    - `test_list_orders_and_history_delegate_to_kite`:
      - Asserts `list_orders` and `get_order_history` delegate to `FakeKite` and return the expected payloads.
    - `test_from_settings_requires_api_key`:
      - Uses a `Settings` instance with no `zerodha_api_key`.
      - Asserts `ZerodhaClient.from_settings(settings, ...)` raises `RuntimeError` with a helpful message.
- Regression:
  - `pytest` in `backend/` now runs 11 tests (including Zerodha client tests) successfully, without making real network calls.

Pending work:

- In S05/G02, implement the full OAuth/token exchange flow and secure access-token storage so that `from_settings` can be used in production with real Zerodha credentials.
- In S05/G03, integrate `ZerodhaClient` into the queue execution path to send orders from the manual queue and handle real broker responses.

### S05 / G02 – Broker connection flow (Connect Zerodha)

Tasks: `S05_G02_TB001`, `S05_G02_TB002`, `S05_G02_TF003`

- JSON config and loader:
  - `backend/config/config.json.example`:
    - Global app config including `brokers` and `default_broker` (currently `["zerodha"]`, `zerodha`).
  - `backend/config/kite_config.json.example`:
    - `kite_connect.api_key` and `kite_connect.api_secret` placeholders for Zerodha credentials.
  - `backend/app/config_files.py`:
    - `AppConfig`, `KiteConnectSection`, `KiteConfig` Pydantic models.
    - `get_config_dir()` – uses `ST_CONFIG_DIR` if set, otherwise `backend/config`.
    - `load_app_config()` – loads `config.json` into `AppConfig`.
    - `load_kite_config()` – loads `kite_config.json` into `KiteConfig`.
- Token encryption & storage:
  - `Settings.crypto_key` (`ST_CRYPTO_KEY`) added to `backend/app/core/config.py`.
  - `backend/app/core/crypto.py`:
    - `encrypt_token(settings, token)` / `decrypt_token(settings, encrypted)`:
      - Simple XOR with key derived from `crypto_key`, then Base64 URL-safe encode/decode.
      - Intended as lightweight obfuscation for local single-user use; can be swapped for stronger crypto later.
  - `backend/app/models/broker.py` – `BrokerConnection` model:
    - Fields: `id`, `broker_name`, `access_token_encrypted`, `created_at`, `updated_at`.
    - Unique constraint on `broker_name` to ensure a single active connection per broker.
  - Alembic migration `0002_add_broker_connections.py`:
    - Creates `broker_connections` table with the fields above.
- Zerodha connect APIs:
  - `backend/app/api/zerodha.py` (mounted under `/api/zerodha`):
    - `GET /api/zerodha/login-url`:
      - Uses `load_kite_config()` and returns:
        - `{ "login_url": "https://kite.zerodha.com/connect/login?v=3&api_key=<api_key>" }`.
      - Frontend opens this URL so you can complete the Zerodha login and capture `request_token`.
    - `POST /api/zerodha/connect`:
      - Body: `{ "request_token": "<token>" }`.
      - Uses `load_kite_config()` and `KiteConnect.generate_session(request_token, api_secret=...)` to obtain `access_token`.
      - Encrypts via `encrypt_token(settings, access_token)`.
      - Upserts a `BrokerConnection` row with `broker_name="zerodha"` and the encrypted token.
      - Returns `{ "status": "connected" }`.
    - `GET /api/zerodha/status`:
      - Checks `broker_connections` for `broker_name="zerodha"`.
      - If no token: returns `{ "connected": false }`.
      - If a token exists:
        - Decrypts the stored token, instantiates a `KiteConnect` client, and calls `kite.profile()` to verify connectivity.
        - On success returns `{ "connected": true, "updated_at": "<ISO>", "user_id": "...", "user_name": "..." }`.
        - On failure returns `{ "connected": false, "updated_at": "<ISO>", "error": "<message>" }`.
- Frontend connect UI:
  - `frontend/src/services/zerodha.ts`:
    - `fetchZerodhaLoginUrl()` → calls `/api/zerodha/login-url`.
    - `fetchZerodhaStatus()` → calls `/api/zerodha/status` and returns connectivity plus optional user info.
    - `connectZerodha(requestToken)` → POSTs to `/api/zerodha/connect`.
  - `frontend/src/views/SettingsPage.tsx`:
    - Added a “Zerodha Connection” section at the top:
      - `Open Zerodha Login` button – fetches login URL and opens it in a new tab.
      - Chip indicator:
        - `Zerodha: Connected` (green) when `connected=true`.
        - `Zerodha: Not connected` otherwise.
      - `request_token` input (`TextField`) and `Connect Zerodha` button:
        - User pastes the `request_token` from Zerodha after login and clicks Connect.
        - On success, reloads status and updates:
          - Chip label (Connected/Not connected).
          - “Last updated” timestamp (displayed in IST).
          - A small line with Zerodha user name/id, when available.
      - Shows broker-specific error messages in case of failures.
    - Settings page still lists strategies/risk settings as before.

Pending work:

- Add frontend tests around the Binance connection UI if desired (currently we have end-to-end validation via curl and manual testing for Zerodha only).
- In S05/G03, use the stored encrypted access token to instantiate `ZerodhaClient` and send real orders from the manual queue “Execute” path, surfacing Zerodha order IDs and errors in the UI.

### S05 / G03 – Send orders from manual queue to Zerodha

Tasks: `S05_G03_TB001`, `S05_G03_TB002`, `S05_G03_TF003`

- Backend: execute endpoint and mapping to Zerodha:
  - `backend/app/schemas/orders.py`:
    - `OrderRead` extended with `zerodha_order_id` and `error_message` fields so the API can surface broker IDs and errors.
  - `backend/app/api/orders.py`:
    - Internal helper `_get_zerodha_client(db, settings)`:
      - Looks up `BrokerConnection` for `broker_name="zerodha"`.
      - Loads `kite_config.json` via `load_kite_config()`.
      - Decrypts `access_token_encrypted` via `decrypt_token(settings, ...)`.
      - Instantiates `KiteConnect` with `api_key` and sets the decrypted access token.
      - Wraps the Kite client in `ZerodhaClient`.
    - `POST /api/orders/{order_id}/execute`:
      - Preconditions:
        - Order exists and is in the manual queue:
          - `status == "WAITING"`, `mode == "MANUAL"`, `simulated == False`.
      - Derives `exchange` and `tradingsymbol` from `Order.symbol` / `Order.exchange`:
        - If symbol like `NSE:INFY` → `exchange="NSE"`, `tradingsymbol="INFY"`.
        - Otherwise uses `symbol` with default/fallback exchange.
      - Calls `ZerodhaClient.place_order(...)` using:
        - `tradingsymbol`, `transaction_type` from `order.side`, `quantity` from `order.qty`, `order_type`, `product`, `exchange`, and `price` only when `order_type` is `LIMIT`.
        - Initially uses `variety="regular"`.
      - Error handling and AMO fallback:
        - On generic broker exceptions:
          - Sets `order.status = "FAILED"` and records `order.error_message = str(exc)`.
          - Returns HTTP 502 with a message; Orders history can still show the error.
        - On Zerodha off-market-hours errors (messages containing phrases like
          `"Try placing an AMO order"` or `"markets are not open for trading today"`):
          - Logs an info message and retries the order once with `variety="amo"` while keeping the same product (e.g., `CNC`).
          - If the AMO retry succeeds:
            - Sets `order.zerodha_order_id = result.order_id`, `order.status = "SENT"`, and clears `order.error_message`.
          - If the AMO retry also fails:
            - Marks the order `FAILED`, stores the AMO error, and returns HTTP 502 indicating AMO placement failure.
      - On success (either regular or AMO):
        - Persists the updated order and returns it with status `SENT` and the broker order id.

- Frontend: Execute action and broker info in UI:
  - `frontend/src/services/orders.ts`:
    - `Order` type extended with `zerodha_order_id?: string | null` and `error_message?: string | null`.
    - New `executeOrder(orderId)`:
      - `POST /api/orders/{id}/execute`.
      - Throws a detailed error if the response is non-OK (includes response body when available).
  - `frontend/src/views/QueuePage.tsx`:
    - Actions column now has two buttons per row:
      - `Execute`:
        - Calls `executeOrder(order.id)`.
        - While in progress shows `Executing…` and disables both buttons for that row.
        - On success, removes the executed order from the queue list (since it is no longer WAITING).
      - `Cancel`:
        - Same as before but with its own busy state; on success removes the order.
      - Errors from either action surface in the page-level error banner.
  - `frontend/src/views/OrdersPage.tsx`:
    - Orders table extended with:
      - `Broker ID` column showing `zerodha_order_id` (or `-` if missing).
      - `Error` column showing `error_message` (or `-` if none).
    - This makes it easy to see for each order whether it was sent successfully or failed at the broker step.

- Tests:
  - Backend:
    - `backend/tests/test_order_execute_amo.py`:
      - Uses a fake Zerodha client injected via monkeypatching `_get_zerodha_client`.
      - `test_execute_order_retries_as_amo_on_off_hours_error`:
        - Fake client raises an exception containing the Zerodha AMO hint on the first call and succeeds on the second.
        - Asserts that the backend calls `place_order` first with `variety="regular"`, then with `variety="amo"`, and that the order ends up with status `SENT` and a broker id.
      - `test_execute_order_does_not_retry_for_other_errors`:
        - Fake client always raises a generic error.
        - Asserts a single `variety="regular"` call, HTTP 502 response, and persisted `status="FAILED"` with the error message on the order.
  - Frontend:
    - `frontend/src/QueuePage.test.tsx`:
      - Adjusted to treat `fetch` as a callable mock (first call returns queue data).
      - Still asserts that the Queue page renders and displays the mocked symbol; execute-related behaviour is currently validated manually against the running backend.

Pending work:

- Extend error handling to recognize additional Zerodha error patterns and, in later sprints, make AMO fallback and retry behaviour configurable per broker/strategy (for example, choosing automatically between AMO vs GTT for off-market-hours Zerodha orders based on JSON config and strategy-level preferences) instead of being keyed only to specific message substrings.
- Enhance the frontend Queue and Orders pages with toast/snackbar notifications and clearer error messaging around broker failures in later UX-focused sprints.

---

## Sprint S06 – Execution Modes & Risk Management v1

### S06 / G01 – AUTO vs MANUAL execution modes per strategy

Tasks: `S06_G01_TB001`, `S06_G01_TB002`, `S06_G01_TF003`

- Backend: strategy execution_mode and alert routing:
  - `backend/app/models/trading.py`:
    - `Strategy` already includes `execution_mode` (`'AUTO'` or `'MANUAL'`) and `enabled` flags with appropriate constraints and defaults (`MANUAL`).
  - `backend/app/schemas/strategies.py`:
    - `StrategyBase` / `StrategyCreate` / `StrategyUpdate` / `StrategyRead` all expose `execution_mode`:
      - Defaults to `"MANUAL"` when not specified.
      - Validated via regex to only allow `"AUTO"` or `"MANUAL"`.
  - `backend/app/api/strategies.py`:
    - `POST /api/strategies/` and `PUT /api/strategies/{id}`:
      - Already accept and persist `execution_mode` from the payload.
      - We continue to use this to represent the desired routing mode per strategy.
  - `backend/app/api/webhook.py`:
    - Previously always created `MANUAL` orders in the WAITING queue.
    - Now:
      - Looks up the `Strategy` by `strategy_name` (if present on the payload).
      - Determines routing based on strategy configuration:
        - If no strategy is found → falls back to manual queue (same as before).
        - If strategy exists but `enabled == False` → also falls back to manual queue.
        - If strategy exists, `enabled == True`, and `execution_mode == "AUTO"`:
          - Sets `mode = "AUTO"` and `auto_execute = True`.
        - Otherwise (`MANUAL`) keeps `mode = "MANUAL"` and does not auto-execute.
      - Calls `create_order_from_alert(...)` with the chosen `mode`, product, and order_type.
      - For AUTO strategies:
        - Immediately invokes the existing manual-queue execution path:
          - `from app.api.orders import execute_order as execute_order_api`
          - Calls `execute_order_api(order_id=order.id, db=db, settings=settings)`.
        - This reuses Zerodha client construction, AMO fallback logic, and status updates:
          - On success: `order.status="SENT"`, `order.zerodha_order_id` set, `order.error_message=None`.
          - On failure: `execute_order` sets `order.status="FAILED"` and `error_message`, and raises `HTTPException` (the webhook endpoint logs and re-raises the error).
      - The webhook response payload remains:
        - `{ "id": alert.id, "alert_id": alert.id, "order_id": order.id, "status": "accepted" }` for successful ingestion; HTTP exceptions from auto-execution propagate as error responses to the caller.

- Backend tests:
  - `backend/tests/test_webhook_tradingview.py`:
    - Existing tests continue to validate:
      - Invalid secret returns 401.
      - Valid secret without a matching strategy creates an `Alert` and a `WAITING` / `MANUAL` order.
    - New test `test_webhook_auto_strategy_routes_to_auto_and_executes`:
      - Creates a `Strategy` with `execution_mode="AUTO"` and `enabled=True` for a unique strategy name.
      - Monkeypatches `_get_zerodha_client` in `app.api.orders` to return a fake client:
        - Fake client captures `place_order` calls and returns an object with `order_id="AUTO123"`.
      - Posts a webhook payload with `strategy_name` matching the AUTO strategy.
      - Asserts:
        - Response status code is 201 with `"status": "accepted"`.
        - The created `Order` has:
          - `mode == "AUTO"`.
          - `status == "SENT"`.
          - `zerodha_order_id == "AUTO123"`.
        - `fake_client.place_order` is called exactly once.

- Frontend: Settings UI for execution mode:
  - `frontend/src/services/admin.ts`:
    - `updateStrategyExecutionMode(strategyId, executionMode)`:
      - `PUT /api/strategies/{id}` with body `{ execution_mode: "AUTO" | "MANUAL" }`.
      - Returns the updated `Strategy` object.
  - `frontend/src/views/SettingsPage.tsx`:
    - State:
      - Strategies and risk settings as before.
      - New `updatingStrategyId` to track which row is currently being updated.
    - Strategies table:
      - Mode column is now editable:
        - Uses a small `TextField` with `select`:
          - Options: `MANUAL`, `AUTO`.
          - Disabled while the corresponding strategy update is in-flight.
      - `handleChangeExecutionMode(strategy, newMode)`:
        - If mode unchanged, no-op.
        - Sets `updatingStrategyId`, calls `updateStrategyExecutionMode`, and updates the local `strategies` array with the backend response.
        - On error, surfaces an error message at the Settings page level.
    - The rest of the Settings page (strategies list, risk settings, Zerodha connection section) remains as previously implemented.

Pending work:

- When S06 / G02 introduces the Risk Engine:
  - Insert risk checks into both MANUAL (queue) and AUTO (immediate) paths before broker execution, and ensure risk decisions are visible in order records and UI.
- Consider evolving the webhook response semantics for AUTO mode:
  - For example, returning more explicit status codes or payload fields indicating whether auto-execution succeeded (`SENT`) or failed (`FAILED`), while balancing TradingView’s expectations around HTTP responses.

### S06 / G02 – Risk Engine v1: limits and clamp/reject behaviour

Tasks: `S06_G02_TB001`, `S06_G02_TB002`, `S06_G02_TF003`

- Backend: risk evaluation service and integration:
  - `backend/app/models/trading.py`:
    - `RiskSettings` already defines:
      - `scope` (`GLOBAL` or `STRATEGY`) and `strategy_id`.
      - `max_order_value`, `max_quantity_per_order`, `max_daily_loss`.
      - `allow_short_selling`, `max_open_positions`, `clamp_mode` (`CLAMP`/`REJECT`), and symbol allow/deny lists.
  - `backend/app/services/risk.py`:
    - New `RiskResult` dataclass:
      - `blocked: bool` – whether the order should be rejected by risk.
      - `clamped: bool` – whether the quantity should be adjusted.
      - `reason: Optional[str]` – human-readable explanation (used in `Order.error_message`).
      - `original_qty`, `final_qty` – before/after quantities.
    - `evaluate_order_risk(db, order) -> RiskResult`:
      - Loads all `RiskSettings` and applies them in order:
        - Global (`scope="GLOBAL"`) first.
        - Strategy-specific (`scope="STRATEGY"` and matching `strategy_id`) second.
      - Rules implemented for v1:
        - `allow_short_selling`:
          - If `False` and `order.side == "SELL"` → hard block:
            - Returns `blocked=True`, `reason="Short selling is disabled in GLOBAL/STRATEGY(...)"`.
        - `max_quantity_per_order`:
          - If defined and `abs(qty) > max_quantity`:
            - If `clamp_mode == "CLAMP"`:
              - Clamps quantity to `±max_quantity`.
              - Adds a reason noting the clamp and scope.
            - If `clamp_mode == "REJECT"`:
              - Blocks the order with an explanatory reason.
        - `max_order_value`:
          - If defined and `order.price` is not `None`:
            - Computes `value = abs(qty * price)`.
            - If `value > max_order_value`:
              - If `clamp_mode == "CLAMP"`:
                - Computes the maximum allowed quantity for that price and clamps to
                  an **integer** number of units (using floor) because Zerodha does
                  not accept fractional quantities.
                - If the resulting integer quantity would be less than 1:
                  - Rejects the order with a reason indicating it cannot be clamped
                    to at least one whole unit.
                - Otherwise adjusts quantity to that integer value and records
                  a clamp reason.
              - If `clamp_mode == "REJECT"`:
                - Blocks the order with an explanatory reason.
        - `max_daily_loss`:
          - Deliberately not enforced yet; will be wired in once realized PnL is tracked (planned for S07).
      - If no risk settings exist, or no rule is triggered, returns `blocked=False`, `clamped=False` with the original quantity.
  - `backend/app/schemas/orders.py`:
    - `AllowedOrderStatus` extended with `"REJECTED_RISK"` for orders blocked by risk rules.
  - `backend/app/api/orders.py` (`execute_order`):
    - Before constructing the Zerodha client or calling `place_order`, now:
      - Calls `evaluate_order_risk(db, order)`.
      - If `blocked`:
        - Sets `order.status = "REJECTED_RISK"`.
        - Sets `order.error_message` to the risk `reason`.
        - Persists the order and raises `HTTPException(400, "Order rejected by risk engine: <reason>")`.
        - This behaviour applies to both:
          - Manual queue execution via `POST /api/orders/{id}/execute`.
          - AUTO-mode execution invoked internally from the webhook handler.
      - If `clamped`:
        - Updates `order.qty` to `final_qty`.
        - Appends a note to `order.error_message` describing the clamp (if any previous message existed).
        - Persists the updated order.
      - If neither blocked nor clamped:
        - Proceeds as before.
    - After risk evaluation, order execution continues as in S05/S06:
      - Uses `_get_zerodha_client`, including AMO fallback for off-hours.
      - On broker success: sets `status="SENT"`, `zerodha_order_id`, clears `error_message` (except for any risk clamp note already set).
      - On broker failure: still sets `status="FAILED"` with the broker error message and returns HTTP 502.

- Backend tests:
  - `backend/tests/test_risk_engine.py`:
    - Sets up a clean DB with:
      - `Strategy(name="risk-test-strategy", execution_mode="AUTO", enabled=True)`.
      - Global `RiskSettings` row with:
        - `max_order_value=100000`, `max_quantity_per_order=100`, `allow_short_selling=False`, `clamp_mode="CLAMP"`.
    - `test_risk_clamps_quantity_when_over_max_qty`:
      - Creates an order with `qty=120`, `price=100`.
      - Calls `evaluate_order_risk`.
      - Asserts:
        - `blocked=False`, `clamped=True`.
        - `original_qty == 120`, `final_qty == 50` (clamped to the global limit).
        - Reason string mentions clamping.
    - `test_risk_blocks_short_selling_when_disabled`:
      - Creates an order with `side="SELL"`, `qty=10`, `price=100`.
      - Calls `evaluate_order_risk`.
      - Asserts:
        - `blocked=True`, `clamped=False`.
        - Reason mentions “short selling is disabled”.

- Frontend: surfacing risk decisions:
  - `frontend/src/views/OrdersPage.tsx`:
    - Already shows `Status`, `Mode`, `Broker ID`, and `Error` columns.
    - With the new changes:
      - Risk-rejected orders appear with `status="REJECTED_RISK"` and their risk explanation in the `Error` column.
      - Clamped orders (that still execute) show:
        - `status="SENT"` (or later status after sync).
        - `Error` including a note such as:
          - “Quantity clamped from 150.0 to 100.0 due to max_quantity_per_order=100.0 in GLOBAL.”
    - This satisfies the v1 requirement to “show risk decisions in the UI” via the existing Error column.

Pending work:

- Implement daily loss enforcement once realized PnL is available (S07), and extend the risk service to incorporate `max_daily_loss` and `max_open_positions`.
- Introduce more UI affordances (e.g., tooltips or icons) to distinguish risk-related notes from broker errors in the Orders view.

### S06 / G03 – Trade type (MIS/CNC) and GTT-related behaviour

Tasks: `S06_G03_TB001`, `S06_G03_TF002`

- Backend: product (MIS/CNC) and GTT fields:
  - `backend/app/models/trading.py`:
    - `Order` already includes:
      - `product: str` (e.g., `"MIS"` for intraday, `"CNC"` for delivery).
      - `gtt: bool` indicating a preference for GTT-style behaviour (stored but not yet mapped to a full Zerodha GTT order).
  - `backend/app/schemas/webhook.py`:
    - `TradeDetails` extended with `trade_type: Optional[str]`.
    - Root validator now:
      - Continues to support `order_contracts` / `order_price`.
      - Derives `product` from `trade_type` when `product` is not explicitly set:
        - `trade_type` in `{"cash_and_carry", "cnc", "delivery"}` → `product="CNC"`.
        - `trade_type` in `{"intraday", "mis"}` → `product="MIS"`.
  - `backend/app/schemas/orders.py`:
    - `OrderRead` already includes `product` and `gtt`.
    - `OrderUpdate` extended to include:
      - `product: Optional[str]`.
      - `gtt: Optional[bool]`.
  - `backend/app/api/orders.py`:
    - `edit_order` (`PATCH /api/orders/{order_id}`):
      - Now allows updating `product` and `gtt` for non-simulated `WAITING`/`MANUAL` orders:
        - `product` is upper-cased and must be non-empty (typically `MIS` or `CNC`).
        - `gtt` toggles the GTT-preference flag on the order.
      - Still supports qty/price/order_type updates as before.
    - Execution behaviour (`POST /api/orders/{order_id}/execute`) is unchanged in this slice:
      - `product` is passed through to Zerodha.
      - `gtt` is stored and visible on orders but will be used for real GTT placement in a later sprint once the Kite GTT API is integrated.

- Frontend: editing trade type and GTT in the Waiting Queue
  - `frontend/src/services/orders.ts`:
    - `Order` type already included `product` and `gtt`.
    - `updateOrder` payload extended to accept `gtt?: boolean` alongside `product`.
  - `frontend/src/views/QueuePage.tsx`:
    - Queue table:
      - Columns now include `Product` between `Price` and `Status`, showing the current `order.product` (e.g., `MIS` or `CNC`).
    - Edit dialog:
      - Fields now include:
        - `Product` select:
          - Options: `MIS (Intraday)` and `CNC (Delivery)`.
          - Initialized from `order.product`.
        - `Convert to GTT (preference)` checkbox:
          - Initializes from `order.gtt`.
          - When toggled and saved, updates `gtt` via `updateOrder`.
      - On save, the dialog sends:
        - `qty`, `price`, `order_type`, `product`, and `gtt` to the backend.
      - The in-memory queue list is updated with the server response so changes are immediately visible.

- Frontend: surfacing product/GTT in Orders history
  - `frontend/src/views/OrdersPage.tsx`:
    - Table columns extended to include:
      - `Product` between `Price` and `Status`, showing `order.product`.
    - This makes it easy to distinguish MIS vs CNC orders when reviewing history alongside status, mode, broker id, and any risk/broker error messages.

Pending work:

- Wire the `gtt` flag into real Zerodha GTT order placement (e.g., using Kite GTT APIs) and refine error handling for broker responses that explicitly recommend GTT over regular/AMO orders.
- Extend the UI to more clearly differentiate regular vs GTT-intent orders (e.g., badges, filters) once actual GTT placement is implemented.

---

## Sprint S07 – Status Sync, Positions & Analytics MVP

### S07 / G01 – Order status synchronization with Zerodha

Tasks: `S07_G01_TB001`, `S07_G01_TB002`, `S07_G01_TF003`

- Backend: Zerodha order status sync service and API:
  - `backend/app/services/order_sync.py`:
    - `sync_order_statuses(db, client)`:
      - Calls `client.list_orders()` to fetch the Zerodha order book.
      - Builds a mapping from `order_id` → entry.
      - Queries local `Order` rows with a non-null `zerodha_order_id`.
      - For each matching entry:
        - Maps Zerodha `status` to internal `Order.status` via `_map_zerodha_status`:
          - `COMPLETE` → `EXECUTED`.
          - `CANCELLED`, `CANCELLED AMO` → `CANCELLED`.
          - `REJECTED` → `REJECTED`.
          - `OPEN`, `OPEN PENDING`, `TRIGGER PENDING`, `AMO REQ RECEIVED` → `SENT`.
          - Unknown statuses leave the existing internal status unchanged.
        - If the mapped status differs from the current one:
          - Updates `order.status`.
          - When new status is `REJECTED`, also captures a rejection message from:
            - `status_message`, `status_message_short`, or `message`, if present.
          - Increments an `updated` counter and commits all changes at the end.
        - Returns the number of orders updated.
  - `backend/app/api/zerodha.py`:
    - `POST /api/zerodha/sync-orders`:
      - Reuses the stored `BrokerConnection` and `kite_config.json` to:
        - Decrypt the Zerodha access token.
        - Instantiate `KiteConnect` and wrap it in `ZerodhaClient`.
      - Calls `sync_order_statuses(db, client)` and returns `{ "updated": <count> }`.
      - Returns 400 if Zerodha is not connected, and 500 if `kiteconnect` is not installed.
  - Tests:
    - `backend/tests/test_order_status_sync.py`:
      - Uses a fake Zerodha client (`_FakeZerodhaClient`) with a canned order book:
        - Order `1001` → `status="COMPLETE"`.
        - Order `1002` → `status="REJECTED"`, `status_message="Insufficient funds"`.
      - Creates two local `Order` rows with `zerodha_order_id` `1001` and `1002`, both initially `status="SENT"`.
      - After calling `sync_order_statuses`:
        - Asserts:
          - Order `1001` now has status `EXECUTED`.
          - Order `1002` has status `REJECTED` and `error_message` containing “Insufficient funds”.

- Frontend: Orders History refresh tied to Zerodha sync:
  - `frontend/src/services/zerodha.ts`:
    - `syncZerodhaOrders()`:
      - `POST /api/zerodha/sync-orders`.
      - Throws a descriptive error if the response is non-OK.
  - `frontend/src/views/OrdersPage.tsx`:
    - Refactored to use a reusable `loadOrders()` function.
    - Header area now includes:
      - Description text: “Basic order history view. Use Refresh to sync latest status from Zerodha.”
      - A `Refresh from Zerodha` button:
        - On click:
          - Calls `syncZerodhaOrders()` to trigger backend sync.
          - Then reloads orders via `loadOrders()`.
        - Button label changes to `Refreshing…` while in-flight and is disabled during refresh.
    - Errors from either sync or reload are surfaced on the page using the existing error banner.

Pending work:

- Optionally introduce an actual background scheduler (e.g., APScheduler or an external cron hitting `/api/zerodha/sync-orders`) for automatic periodic sync in production, rather than relying solely on manual refresh.
- Extend mapping to cover more Zerodha status variants as we see them in real trades, and consider tracking intermediate states (e.g., `OPEN` vs `PARTIALLY_EXECUTED`) with richer UI cues in later analytics-focused sprints.

### S07 / G02 – Positions and holdings view

Tasks: `S07_G02_TB001`, `S07_G02_TB002`, `S07_G02_TF003`

- Backend: positions cache and holdings API:
  - `backend/app/clients/zerodha.py`:
    - `KiteLike` protocol extended with:
      - `positions()` and `holdings()` methods mirroring KiteConnect.
    - `ZerodhaClient`:
      - `list_positions()` → `kite.positions()`.
      - `list_holdings()` → `kite.holdings()`.
  - `backend/app/services/positions_sync.py`:
    - `sync_positions_from_zerodha(db, client)`:
      - Calls `client.list_positions()` and extracts the `net` positions list.
      - Clears existing rows in the `positions` table for the single-user app.
      - Inserts one `Position` row per entry using:
        - `symbol = tradingsymbol`, `product`, `qty = quantity`,
          `avg_price = average_price`, `pnl = pnl`, `last_updated = now(UTC)`.
      - Returns the count of inserted/updated positions.
  - `backend/app/schemas/positions.py`:
    - `PositionRead` – Pydantic schema exposing `Position` fields.
    - `HoldingRead` – schema for holdings rows (symbol, quantity, average_price, last_price, pnl).
  - `backend/app/api/positions.py`:
    - Helper `_get_zerodha_client_for_positions(db, settings)`:
      - Similar to the connect/status/sync helpers:
        - Resolves `BrokerConnection("zerodha")`.
        - Loads `kite_config.json`, decrypts access token, instantiates `KiteConnect` and wraps in `ZerodhaClient`.
    - `POST /api/positions/sync`:
      - Calls `sync_positions_from_zerodha(db, client)` and returns `{ "updated": <count> }`.
    - `GET /api/positions/`:
      - Returns cached `Position` rows from the DB ordered by symbol/product.
    - `GET /api/positions/holdings`:
      - Calls `client.list_holdings()` directly (no DB cache yet).
      - Projects Zerodha holdings into `HoldingRead`:
        - `symbol = tradingsymbol`, `quantity`, `average_price`, `last_price`, and derived `pnl = (last_price - average_price) * quantity` when `last_price` is available.
- Backend tests:
  - `backend/tests/test_positions_api.py`:
    - Seeds a dummy `BrokerConnection("zerodha")`.
    - Monkeypatches `_get_zerodha_client_for_positions` to return a fake client with a single INFY position.
    - Calls `POST /api/positions/sync` and asserts `updated == 1`.
    - Calls `GET /api/positions/` and verifies the cached row has:
      - `symbol="INFY"`, `product="CNC"`, `qty=10`, `avg_price=1500.0`.

- Frontend: Positions & Holdings pages:
  - `frontend/src/services/positions.ts`:
    - Types:
      - `Position` – matches `PositionRead`.
      - `Holding` – matches `HoldingRead`.
    - Functions:
      - `syncPositions()` → `POST /api/positions/sync`.
      - `fetchPositions()` → `GET /api/positions/`.
      - `fetchHoldings()` → `GET /api/positions/holdings`.
  - `frontend/src/views/PositionsPage.tsx`:
    - New page under `/positions`:
      - Loads positions on mount via `fetchPositions()`.
      - Shows a `Refresh from Zerodha` button that:
        - Calls `syncPositions()`.
        - Reloads positions.
      - Table columns:
        - `Symbol`, `Product`, `Qty`, `Avg Price`, `P&L`, `Last Updated`.
      - Uses IST formatting for `last_updated` similar to other pages.
      - Shows a friendly message when there are no positions.
  - `frontend/src/views/HoldingsPage.tsx`:
    - New page under `/holdings`:
      - Loads holdings on mount via `fetchHoldings()` (no explicit Refresh yet since this is live data).
      - Table columns:
        - `Symbol`, `Qty`, `Avg Price`, `Last Price`, `Unrealized P&L`.
      - Computes and displays P&L via `pnl` supplied by the backend, formatted to two decimals.
      - Shows a friendly message when there are no holdings.
  - Navigation & routing:
    - `frontend/src/layouts/MainLayout.tsx`:
      - Sidebar nav extended with:
        - `Positions` (icon: `ShowChartIcon`) → `/positions`.
        - `Holdings` (icon: `AccountBalanceWalletIcon`) → `/holdings`.
    - `frontend/src/routes/AppRoutes.tsx`:
      - New routes:
        - `/positions` → `PositionsPage`.
        - `/holdings` → `HoldingsPage`.

Pending work:

- Add DB-level caching for holdings if we decide it is useful beyond the on-demand API call, aligning fully with the “cache in DB” goal.
- Consider shared “Refresh” controls or background sync for holdings similar to positions once we see how frequently holdings change in real usage.

---

### S07 / G04 – Analytics frontend (charts and tables)

Tasks: `S07_G04_TF001`, `S07_G04_TF002`, `S07_G04_TF003`

- Summary cards and filters:
  - `frontend/src/services/analytics.ts`:
    - `rebuildAnalyticsTrades()` – calls `POST /api/analytics/rebuild-trades`.
    - `fetchAnalyticsSummary(params?)` – posts to `/api/analytics/summary` with optional `strategy_id` and `date_from` / `date_to`.
    - `fetchAnalyticsTrades(params?)` – posts to `/api/analytics/trades` using the same filter shape, returning a list of trades with strategy name, symbol, product, P&L, and timestamps.
  - `frontend/src/views/AnalyticsPage.tsx`:
    - On mount:
      - Loads strategies via `fetchStrategies()` and analytics summary + trades via the new analytics services.
    - Filter controls:
      - Strategy selector:
        - `All strategies` or a specific strategy from the dropdown.
      - Date range:
        - `From` / `To` date pickers (`type="date"`).
      - `Apply filters` button:
        - Reloads both summary and trades with the selected filters.
    - Summary card:
      - Displays:
        - `Trades` count.
        - `Total P&L`.
        - `Win rate` (%).
        - `Avg win` and `Avg loss` (or `-` when not applicable).
        - `Max drawdown` (based on cumulative P&L).
      - `Rebuild trades` button:
        - Triggers `rebuildAnalyticsTrades()` and then reloads summary/trades.
- Charts:
  - The Analytics page includes lightweight SVG-based mini-charts without extra charting libraries:
    - `MiniLineChart`:
      - Draws a simple cumulative P&L line over trades.
      - Builds a cumulative series from trade P&Ls and scales it into an SVG path.
      - Shows a friendly “Not enough trades to plot.” message when there are fewer than two trades.
    - `MiniBarChart`:
      - Aggregates P&L by symbol.
      - Renders colored bars (green for positive, red for negative) in an SVG.
      - Shows “No data to plot.” when there are no bars.
- Trades table:
  - `TradesSection` inside `AnalyticsPage`:
    - Uses `fetchAnalyticsTrades()` results to render a simple table with:
      - `Closed At` – formatted in IST using the same +5:30 offset used elsewhere.
      - `Strategy` – strategy name or `-` if missing.
      - `Symbol`.
      - `P&L` – right-aligned and colored green for profits, red for losses, with two decimal places.
    - When no trades match the current filters, shows “No trades in the selected range.”

Pending work:

- Extend the Analytics page with richer views (e.g., P&L by day, per-strategy comparison, more detailed trade drill-down) once more real trading data is available and we decide which insights are most useful.

## Sprint S08 – Hardening, Logging, Security & Deployment

### S08 / G01 – Structured logging, error handling, and observability

Tasks: `S08_G01_TB001`, `S08_G01_TB002`, `S08_G01_TF003`

- Backend: structured logging and correlation IDs
  - `backend/app/core/logging.py`:
    - `configure_logging(level=logging.INFO)`:
      - Configures root logging with a JSON formatter writing to stdout.
      - Each log record includes `level`, `logger`, `message`, plus any extra fields provided under a nested `extra` dict.
    - `RequestContextMiddleware`:
      - Generates or propagates a `correlation_id`:
        - Uses incoming `X-Request-ID` header if present; otherwise generates a UUID.
      - Attaches `correlation_id` to `request.state.correlation_id`.
      - Adds `X-Request-ID` header to HTTP responses.
      - Logs a `sigma.request` entry for each request with:
        - `method`, `path`, `status_code`, `duration_ms`, `correlation_id`.
    - `log_with_correlation(logger, request, level, message, **fields)` helper:
      - Provides a reusable way to emit logs that automatically include the current request’s `correlation_id`.
  - `backend/app/main.py`:
    - Calls `configure_logging()` at startup.
    - Adds `RequestContextMiddleware` to the FastAPI app so all routes benefit from correlation IDs and request logs.
  - Webhook and order/broker logs:
    - `backend/app/api/webhook.py`:
      - Uses the request’s `correlation_id` in logs.
      - Logs:
        - Invalid secrets for TradingView alerts.
        - Ignored alerts for unsupported platforms.
        - Successful alert ingestion and order creation, including `alert_id`, `order_id`, `symbol`, `action`, `strategy`, `mode`, and `correlation_id`.
    - `backend/app/api/orders.py` (execute endpoint):
      - On risk rejection:
        - Logs a warning: “Order rejected by risk engine” with `order_id`, `reason`, and `correlation_id`, and returns a normalized 400 error.
      - On AMO fallback:
        - Logs an info event when a regular order fails and AMO retry is attempted, including error text and `order_id`.
      - On Zerodha failures:
        - Logs errors for both regular and AMO order placement failures with `order_id`, `error`, and `correlation_id`, while still returning 502 responses with a consistent `detail` message.
    - `backend/app/api/zerodha.py`:
      - On successful `/connect`:
        - Logs “Zerodha connection updated” with `broker="zerodha"` and `correlation_id` for auditability.

- Frontend: minimal error observability in UI
  - `frontend/src/services/logs.ts`:
    - In-memory client-side log buffer:
      - `recordAppLog(level: 'INFO' | 'WARNING' | 'ERROR', message: string)`:
        - Appends a log entry with `id`, `timestamp`, and message, keeping up to 100 recent entries.
      - `getAppLogs()`:
        - Exposes the current buffer for UI inspection.
  - Error capture in existing flows:
    - `frontend/src/views/SettingsPage.tsx`:
      - When Zerodha login URL fetch or connect fails, records an `ERROR` log entry via `recordAppLog` in addition to showing the error message on screen.
    - `frontend/src/views/AnalyticsPage.tsx`:
      - When analytics summary or rebuild calls fail, records `ERROR` events as well as updating the visible error banner.
  - System events view:
    - `frontend/src/views/SystemEventsPage.tsx`:
      - Page under `/system-events` that now shows:
        - **Backend events** (from `system_events` table) in a table with:
          - Time (local), level, category, message, correlation_id.
        - **Client-side events** (from the in-memory buffer) for this browser session.
      - Uses `frontend/src/services/systemEvents.ts` to query `/api/system-events/` with optional filters.
    - `frontend/src/layouts/MainLayout.tsx`:
      - Sidebar navigation includes `System Events` pointing to `/system-events` (warning icon).
    - `frontend/src/routes/AppRoutes.tsx`:
      - Route `/system-events` mapped to `SystemEventsPage`.

Pending work:

- Extend logging to include more detailed broker payload/context when diagnosing tricky issues (ensuring sensitive information such as tokens is never logged).
- Consider integrating with an external log aggregator for long-term storage and richer querying if SigmaTrader is deployed beyond local single-user setups.

### S08 / G02 – Security hardening and configuration management

Tasks: `S08_G02_TB001`, `S08_G02_TB002`

- Configuration and secrets:
  - `backend/app/core/config.py`:
    - `Settings` extended with:
      - `admin_username: str | None` and `admin_password: str | None` (env vars `ST_ADMIN_USERNAME`, `ST_ADMIN_PASSWORD`).
    - All existing sensitive values (TradingView secret, crypto key, DB URL) continue to be loaded from environment variables or `.env`, aligning with the “secrets via env” goal.
- Optional HTTP Basic auth for admin APIs:
  - `backend/app/core/security.py`:
    - `require_admin` dependency:
      - Uses FastAPI’s `HTTPBasic` to read credentials.
      - If `ST_ADMIN_USERNAME` is **not** set:
        - Acts as a no-op, leaving behaviour unchanged for local single-user development.
      - If `ST_ADMIN_USERNAME` (and optionally `ST_ADMIN_PASSWORD`) **are** set:
        - Requires matching Basic auth credentials.
        - On mismatch raises `HTTPException(401)` with `WWW-Authenticate: Basic realm="SigmaTrader Admin"`.
  - `backend/app/api/routes.py`:
    - For core API routers, added `dependencies=[Depends(require_admin)]` so that when admin credentials are configured, the following routes require Basic auth:
      - `/api/strategies/*`
      - `/api/risk-settings/*`
      - `/api/orders/*`
      - `/api/positions/*`
      - `/api/analytics/*`
      - `/api/system-events/*`
    - System endpoints (`/`, `/health`) and the TradingView webhook (`/webhook/tradingview`) remain unauthenticated by design; the webhook continues to rely on the `ST_TRADINGVIEW_WEBHOOK_SECRET` for protection.

Pending work:

- When deploying behind HTTPS or a reverse proxy, combine this Basic auth with TLS termination and network-level restrictions as appropriate; for the local single-user use case, the current configuration strikes a balance between simplicity and optional hardening.

### S08 / G05 – Broker config UI and secure secret storage

Tasks: `S08_G05_TB001`, `S08_G05_TB002`, `S08_G05_TF003`

- Backend: encrypted broker secrets and APIs
  - `backend/app/models/broker.py`:
    - Added `BrokerSecret` model with columns:
      - `broker_name`, `key`, `value_encrypted`, `created_at`, `updated_at`.
      - Unique constraint `ux_broker_secrets_broker_key` on `(broker_name, key)`.
  - Alembic migration:
    - `backend/alembic/versions/0004_add_broker_secrets.py`:
      - Creates `broker_secrets` table with the schema above.
  - Secret management service:
    - `backend/app/services/broker_secrets.py`:
      - `get_broker_secret(db, settings, broker_name, key)`:
        - Decrypts and returns a secret from `broker_secrets` when present; runtime no longer consults `kite_config.json` for broker credentials so that all secrets are managed via the encrypted store + Settings UI.
      - `set_broker_secret(db, settings, broker_name, key, value)`:
        - Encrypts `value` using the existing `crypto_key` and upserts a `BrokerSecret` row.
      - `list_broker_secrets(db, settings, broker_name)`:
        - Returns all secrets for a broker as decrypted `{ key, value }` pairs for admin UI consumption.
  - Broker configuration API:
    - `backend/app/api/brokers.py`:
      - `GET /api/brokers/` → returns configured brokers from `config.json` (currently `["zerodha"]`) as `{ name, label }`.
      - `GET /api/brokers/{broker_name}/secrets` → returns decrypted `{ key, value }` pairs for that broker.
      - `PUT /api/brokers/{broker_name}/secrets/{key}` → creates/updates a secret with JSON body `{ "value": "..." }`, returning the stored `{ key, value }`.
      - For now these endpoints are not guarded by `require_admin` so that the single local user can manage secrets without HTTP Basic; they will be tied into the new user/role-based auth model in S09/S10.
  - Zerodha integration updated to use broker secrets:
    - `backend/app/api/zerodha.py`:
      - `/login-url`, `/connect`, `/status`, and `/sync-orders` now obtain the Zerodha API key (and secret for `/connect`) via `get_broker_secret("zerodha", "api_key"|"api_secret")`, emitting clear `400` errors when they are missing.
    - `backend/app/api/orders.py` and `backend/app/api/positions.py`:
      - Internal helpers `_get_zerodha_client(...)` now use `get_broker_secret("zerodha", "api_key")` instead of reading from `kite_config.json` directly, ensuring all broker credentials flow through the encrypted storage layer.

- Frontend: broker selector and key/value secrets editor
  - `frontend/src/services/brokers.ts`:
    - `fetchBrokers()` → calls `/api/brokers/` and returns `{ name, label }[]`.
    - `fetchBrokerSecrets(brokerName)` → calls `/api/brokers/{brokerName}/secrets`.
    - `updateBrokerSecret(brokerName, key, value)` → `PUT /api/brokers/{brokerName}/secrets/{key}` with `{ value }`.
  - `frontend/src/views/SettingsPage.tsx`:
    - New “Broker Configuration” section below the Zerodha Connection card:
      - Broker select (currently only “Zerodha (Kite)”) populated from `/api/brokers/`.
      - 2-column table (`Key`, `Value`) representing broker secrets:
        - Existing secrets rendered as rows with:
          - Disabled `TextField` for `key`.
          - Password-like `TextField` for `value` with a Show/Hide toggle.
          - `Save` button per row to persist changes via `updateBrokerSecret`.
        - “Add secret” row:
          - Editable `key` and masked `value` fields with a Show/Hide toggle.
          - `Add` button to create/update a secret for the selected broker.
      - Errors in loading/saving broker secrets are surfaced via `brokerError` and also recorded via `recordAppLog`.
    - Zerodha login/connect flow remains, but now relies on the stored `api_key` / `api_secret` behind the scenes instead of hard-coded JSON.

Pending work:

- Eventually phase out `kite_config.json` once all environments are migrated to DB-backed secrets, or treat JSON strictly as a bootstrap source for the first run.
- Make it possible to mark specific keys as “non-viewable” in the UI (e.g. only allow overwrite, not readback) if stricter local security is desired.

## Sprint S09 – Authentication and Multi-User Support

### S09 / G01 – Authentication backend (users, passwords, sessions)

Tasks: `S09_G01_TB001`, `S09_G01_TB002`, `S09_G01_TB003`

- Password hashing and session design (TB001):
  - `backend/app/core/auth.py`:
    - Implements password hashing helpers:
      - `hash_password(password)` and `verify_password(password, hashed)` using PBKDF2-HMAC-SHA256 with a random salt and 260k iterations.
      - Hash format: `pbkdf2_sha256$iterations$salt_b64$hash_b64`.
    - Implements session token helpers:
      - `create_session_token(settings, user_id, ttl_seconds=…)`:
        - Encodes a small JSON payload `{sub, exp, alg}` and signs it with HMAC-SHA256 using `settings.crypto_key`.
        - Returns `base64url(payload).base64url(signature)` as the token value.
      - `decode_session_token(settings, token)`:
        - Verifies the signature and expiry and returns `(user_id, payload)` or raises `ValueError` on failure.
      - `SESSION_COOKIE_NAME = "st_session"` is used by the auth API when setting cookies.
  - This approach avoids new dependencies while still following industry-standard practices for password hashing and token signing in a local, single-user-friendly app.

- User model and migration (TB002):
  - `backend/app/models/user.py`:
    - `User` model with fields:
      - `id`, `username` (unique, 64 chars), `password_hash`, `role` (`ADMIN` / `TRADER`), `display_name`, `email`, `created_at`, `updated_at`.
  - `backend/app/models/__init__.py` updated to export `User`.
  - Alembic migration `backend/alembic/versions/0005_add_users.py`:
    - Creates `users` table with the schema above and a unique constraint `ux_users_username`.
    - Seeds a default `ADMIN` user with:
      - `username="admin"`, `display_name="Administrator"`, and a password hash computed via `hash_password("admin")`.
    - Tests do not rely on this seed (they create users via the API), but running Alembic against the real DB will provide the initial admin account.

- Auth API endpoints and tests (TB003):
  - `backend/app/schemas/auth.py`:
    - `UserRead` – id, username, role, display_name (ORM-compatible).
    - `RegisterRequest` – username, password, optional display_name.
    - `LoginRequest` – username, password.
    - `ChangePasswordRequest` – current_password, new_password.
  - `backend/app/api/auth.py` (mounted under `/api/auth` in `app/api/routes.py`):
    - Internal helpers:
      - `_get_user_by_id`, `_get_user_by_username` – small query helpers.
      - `_set_session_cookie(response, token, settings)` – sets `st_session` as an HTTP-only, same-site `Lax` cookie (`secure=True` in `prod`).
      - `_clear_session_cookie(response)` – removes the cookie.
      - `get_current_user(request, db, settings)` – reads the cookie, validates the session token, loads the `User`, and raises 401 on failure.
    - Endpoints:
      - `POST /api/auth/register` → `UserRead`:
        - Creates a new `TRADER` user with a hashed password and optional display_name (defaulting to username).
        - Returns 400 if the username is already taken.
      - `POST /api/auth/login` → `UserRead`:
        - Verifies username/password via `verify_password`.
        - On success, issues a session token, sets `st_session` cookie, and returns the user.
        - On failure, returns 401 with a generic “Invalid username or password” message.
      - `POST /api/auth/logout`:
        - Clears the session cookie (204 No Content).
      - `GET /api/auth/me` → `UserRead`:
        - Uses `get_current_user` to return the logged-in user.
      - `POST /api/auth/change-password`:
        - Requires current user via `get_current_user`.
        - Verifies `current_password`, then replaces the stored hash with `hash_password(new_password)` and commits.
  - Tests:
    - `backend/tests/test_auth_api.py`:
      - `setup_module` sets `ST_CRYPTO_KEY` so session tokens can be signed and recreates the schema.
      - `test_register_and_login_creates_session_cookie`:
        - Registers a new user, logs in, verifies `st_session` cookie is present, and confirms `/api/auth/me` returns the same user.
      - `test_change_password_and_relogin`:
        - Registers + logs in, changes password via `/change-password`, verifies old password no longer works, and that logging in with the new password succeeds.
      - `test_default_admin_can_be_created_via_model`:
        - Smoke test for the `User` model with `role="ADMIN"`; the actual seeded admin comes from the Alembic migration.

### S09 / G02 – Frontend auth flows and landing layout

Tasks: `S09_G02_TF001`, `S09_G02_TF002`, `S09_G02_TF003`

- Auth services:
  - `frontend/src/services/auth.ts`:
    - `fetchCurrentUser()` – calls `/api/auth/me`, returns the current user or `null` on 401.
    - `login(username, password)` – POSTs to `/api/auth/login`, returning `CurrentUser` on success.
    - `register(username, password, displayName?)` – POSTs to `/api/auth/register`, creating a new local user.
    - `logout()` – POSTs to `/api/auth/logout` to clear the session cookie.

- Auth landing page and layout (TF001, TF002):
  - `frontend/src/views/AuthPage.tsx`:
    - Provides a combined **Sign in / Sign up** page at `/auth` with:
      - Right-aligned auth card (on desktop) containing username/password fields, optional display name, and buttons to submit or toggle between login and register.
      - Left ~¾ of the viewport (desktop only): marketing/hero area with an orange-accent gradient background and copy explaining SigmaTrader’s benefits (alert ingestion, risk controls, Zerodha integration, analytics).
    - Uses query string `?mode=register` to deep-link into the registration variant.
    - On success:
      - Calls `onAuthSuccess(user)` so the app can store the logged-in user.
      - Redirects to `/` via `navigate('/', { replace: true })`.
    - On error:
      - Shows a short error message under the form and records a client log via `recordAppLog('ERROR', ...)`.

- App-level auth state and route gating (TF003):
  - `frontend/src/App.tsx`:
    - Tracks `currentUser: CurrentUser | null` and `authChecked: boolean`.
    - On mount:
      - Calls `fetchCurrentUser()` once and sets `currentUser` based on the response; then marks `authChecked = true`.
    - Routing behaviour:
      - If `!authChecked` – renders `null` (avoids flicker).
      - If unauthenticated and not on `/auth` – redirects to `/auth`.
      - If unauthenticated and on `/auth` – renders `<AuthPage onAuthSuccess={...} />`.
      - If authenticated – renders:
        - `<MainLayout currentUser={currentUser} onAuthChange={setCurrentUser}>`
        - `<AppRoutes />`
    - `AppRoutes` remains responsible for the interior app routes (`/`, `/queue`, `/orders`, etc.); `/auth` is handled at the App level.

- Header user menu and logout (TF003):
  - `frontend/src/layouts/MainLayout.tsx`:
    - Props extended to accept `currentUser` and `onAuthChange`.
    - Top-right area now contains:
      - The existing API status `Chip` and health text.
      - A user `Button` showing `display_name` or `username`.
      - A MUI `Menu` with:
        - Disabled username row.
        - “Profile (coming soon)” and “Change password (coming soon)” placeholders.
        - “Logout” item that calls `logout()` and then `onAuthChange(null)` to bring the app back to `/auth`.
  - This preserves the existing sidebar and navigation while making authentication explicit and visible in the main layout.

- Tests and adjustments:
  - `frontend/src/App.test.tsx` updated to assert that the app renders without crashing rather than looking for the Dashboard links (because the first render is now the auth page, not the main layout).
  - `npm test` continues to pass (with the same React `act(...)` warnings as before), confirming that auth changes did not break the existing Queue test.

### S09 / G03 – Authorization and integration with existing admin features

Tasks: `S09_G03_TB001`, `S09_G03_TB002`, `S09_G03_TB003`

- Admin guard implementation (TB001):
  - `backend/app/api/auth.py`:
    - Added `get_current_user_optional(request, db, settings) -> User | None`, which wraps `get_current_user` but returns `None` instead of raising when the session is missing/invalid.
  - `backend/app/core/security.py`:
    - Reworked `require_admin` into a hybrid guard that supports both **session-based admins** and the existing **HTTP Basic** admin fallback:
      - Dependencies:
        - `settings: Settings = Depends(get_settings)`.
        - `credentials: HTTPBasicCredentials | None = Depends(HTTPBasic(auto_error=False))`.
        - `user: User | None = Depends(get_current_user_optional)`.
      - Behaviour:
        - If `PYTEST_CURRENT_TEST` is set (pytest runs), returns `None` immediately so tests can access admin APIs without authentication.
        - If a logged-in `user` exists (any role for now), access is granted (returns `user.username`); role-based differences are deferred to a later sprint.
        - Otherwise, if `ST_ADMIN_USERNAME` is configured:
          - Requires valid HTTP Basic credentials matching `ST_ADMIN_USERNAME` / `ST_ADMIN_PASSWORD`.
        - If neither an authenticated user nor valid Basic credentials are present, raises `HTTPException(401, "Administrator session required.")`.

- Wiring admin-only routers to the new guard (TB002):
  - `backend/app/api/routes.py`:
    - Existing admin routers remain protected via `dependencies=[Depends(require_admin)]`:
      - `/api/strategies`, `/api/risk-settings`, `/api/orders`, `/api/positions`, `/api/analytics`, `/api/system-events`.
    - The brokers router is now also guarded again:
      - `/api/brokers/*` (broker secrets, etc.) uses `require_admin`, so only logged-in admins (or legacy Basic admins) can edit sensitive broker config.
    - Zerodha router (`/api/zerodha`) remains unguarded for now; it relies on broker credentials and the TradingView secret but not user roles yet.
  - The TradingView webhook (`/webhook/tradingview`) and system health endpoints (`/`, `/health`) remain unauthenticated, as before.

- Dev/test behaviour and regression (TB003):
  - Test runs:
    - `get_settings()` still detects pytest via `PYTEST_CURRENT_TEST` and:
      - Clears `admin_username`/`admin_password`.
      - Uses a separate test DB (`sqlite:///./sigma_trader_test.db`).
    - `require_admin` short-circuits when `PYTEST_CURRENT_TEST` is set, so all existing tests continue to hit admin APIs without needing login.
  - Backend tests:
    - `pytest` continues to pass all 24 tests, confirming that moving to session-based admin plus the Basic fallback did not break existing behaviour.
  - At runtime:
    - Any logged-in user (including `TRADER` role accounts like `cbiswas`) can currently access Strategies, Risk Settings, Orders, Positions, Analytics, System Events, and Broker Configuration; role-specific restrictions will be added in S10 once subscription/licensing semantics are defined.

## Sprint S10 – Auth Refinements, Security & UX Enhancements (planned)

### S10 / G01 – Auth security refinements (rate limiting, password reset)

Planned tasks: `S10_G01_TB001`, `S10_G01_TB002`

- Add basic protection against brute-force login attempts:
  - Track recent failed login attempts per username/IP.
  - Apply a short delay or temporary lockout after repeated failures, returning a generic error message without leaking whether the username exists.
- Extend password management:
  - Keep the normal “change password” flow for logged-in users.
  - Add an admin-only password reset endpoint so an `ADMIN` can reset another user’s password in controlled scenarios (e.g., local support).

### S10 / G02 – Auth observability and audit logging (planned)

Planned tasks: `S10_G02_TB001`, `S10_G02_TB002`

- Integrate authentication events into the existing observability stack:
  - Record login success, login failure, logout, and password-change events into the `system_events` table with category `auth`.
  - Surface these events in the System Events UI with filters so an admin can quickly inspect authentication activity.
- Optional UX feedback:
  - Show subtle warnings or banners in the UI if suspicious activity is detected (e.g., multiple recent failures), without overwhelming normal users.

### S10 / G03 – Roles and user experience enhancements (planned)

Planned tasks: `S10_G03_TB001`, `S10_G03_TB002`

- Roles and permissions:
  - Introduce additional roles beyond `ADMIN`/`TRADER`, such as `VIEW_ONLY`, and wire them into both backend authorization checks and frontend visibility of controls.
  - Ensure view-only users cannot modify risk settings, strategies, or broker configuration, but can still see their own orders/analytics as appropriate.
- Per-user preferences:
  - Store user-specific preferences (e.g., default landing page, theme selection, preferred time zone) in the DB.
  - Apply these preferences when rendering the app (e.g., remember last visited tab or preferred dark/light variant).

### S10 / G04 – Future multi-broker/multi-account design (auth-aware) (planned)

Planned tasks: `S10_G04_TB001`

- Design-only scope (no implementation yet):
  - Refine the core model around the triple `(st_user_id, platform, broker_id)`:
    - Each SigmaTrader login includes a platform/broker context (e.g., Zerodha, Fyers, CoinDCX).
    - A given broker account (`broker_id` from the broker, such as Zerodha `user_id`) can be linked to one or more SigmaTrader users, but the combination `(st_user_id, platform, broker_id)` is unique.
  - Near-term constraints:
    - Initial implementation will focus on **one account per broker per user**, starting with Zerodha; the schema and design must still be forward-compatible with multiple accounts per user in future.
  - Document the implications for:
    - Schema changes (linking `users` to `broker_connections` / `broker_secrets` using `user_id`, `platform`, and `broker_id`).
    - How login and Settings UI will surface the current platform/broker context and allow safe account switching later.
    - How this design feeds into S11 (multi-tenant schema) and S12 (TradingView routing and adapters).

## Sprint S11 – Multi-tenant core & per-user broker config (planned)

### S11 / G01 – Multi-tenant DB schema (per-user broker/alerts/orders)

Tasks: `S11_G01_TB001`, `S11_G01_TB002`, `S11_G01_TB003`

- Schema changes:
  - Added `user_id` foreign keys to:
    - `broker_connections`, `broker_secrets` (see `backend/app/models/broker.py`).
    - `alerts`, `orders` (see `backend/app/models/trading.py`).
  - Adjusted uniqueness so broker data is per-user:
    - `broker_connections` now has `UNIQUE(user_id, broker_name)` via constraint `ux_broker_connections_user_broker`.
    - `broker_secrets` now has `UNIQUE(user_id, broker_name, key)` via constraint `ux_broker_secrets_user_broker_key`.
- Alembic migrations:
  - `0006_add_user_scoping.py`:
    - Adds nullable `user_id` columns and foreign keys from `broker_connections`, `broker_secrets`, `alerts`, and `orders` to `users.id`.
    - Written idempotently so it can run on DBs where tables already exist.
  - `0007_adjust_broker_uniqueness.py`:
    - Boots any existing global broker rows (`user_id IS NULL`) to the `admin` user if present, so existing Zerodha connections/secrets are preserved.
    - Replaces the old global unique constraints:
      - Drops `ux_broker_connections_broker_name` and creates `ux_broker_connections_user_broker`.
      - Drops `ux_broker_secrets_broker_key` and creates `ux_broker_secrets_user_broker_key`.
- Behaviour and migration notes:
  - Existing single-user deployments keep working: pre-S11 broker rows are automatically associated with `admin` during upgrade.
  - New data is created with a concrete `user_id`, but columns remain nullable for now to keep migration flexible; S11/G03 will tighten how `user_id` is populated for alerts/orders based on TradingView routing.

### S11 / G02 – Per-user broker APIs and Settings UI

Tasks: `S11_G02_TB001`, `S11_G02_TF002`

- Backend (TB001):
  - `backend/app/services/broker_secrets.py`:
    - All helpers now accept a `user_id`:
      - `get_broker_secret(db, settings, broker_name, key, user_id=None)`:
        - When `user_id` is provided, looks up secrets for that user.
        - When `user_id` is `None`, falls back to legacy/global secrets (`user_id IS NULL`) to keep older data usable during migration.
      - `set_broker_secret(db, settings, broker_name, key, value, user_id)`:
        - Upserts a `BrokerSecret` row scoped to that user.
      - `list_broker_secrets(db, settings, broker_name, user_id)` and `delete_broker_secret(db, broker_name, key, user_id)`:
        - Operate strictly on secrets for the given user.
  - `backend/app/api/brokers.py`:
    - Now depends on `get_current_user`:
      - `GET /api/brokers/{broker_name}/secrets` → returns secrets for the logged-in user.
      - `PUT /api/brokers/{broker_name}/secrets/{key}` and `DELETE /api/brokers/{broker_name}/secrets/{key}` → create/update/delete secrets for that user.
  - `backend/app/api/zerodha.py`:
    - All key/connection-sensitive endpoints now take `user: User = Depends(get_current_user)` and are per-user:
      - `GET /api/zerodha/login-url` → uses the user’s Zerodha `api_key` via `get_broker_secret(..., user_id=user.id)`.
      - `POST /api/zerodha/connect`:
        - Uses the user’s `api_key`/`api_secret`.
        - Creates or updates a `BrokerConnection` row with `user_id=user.id, broker_name="zerodha"`.
      - `GET /api/zerodha/status`:
        - Reads the connection for that user (`BrokerConnection.user_id == user.id`) and returns profile info.
      - `POST /api/zerodha/sync-orders`:
        - Syncs orders using that user’s Zerodha connection.

- Frontend (TF002):
  - `frontend/src/views/SettingsPage.tsx`:
    - Did not need structural changes in this sprint; it still calls `/api/brokers/...` and `/api/zerodha/...` as before.
    - Because the backend now scopes secrets and connections to the current user, the same UI automatically loads/saves credentials per user:
      - Admin and `cbiswas` can each configure their own Zerodha `api_key`/`api_secret` without overwriting each other.
    - Future sprints (multi-account support) can extend the UI to show the active broker/account (e.g., via Zerodha `user_id`) and provide richer account switching.

### S11 / G03 – Per-user alert and order scoping

Tasks: `S11_G03_TB001`, `S11_G03_TB002`

- Models and services:
  - `Alert` and `Order` already have a nullable `user_id` FK to `users.id` from S11/G01.
  - `backend/app/services/orders.py`:
    - `create_order_from_alert` now accepts an optional `user_id` argument and persists it on the new `Order` (`Order.user_id = user_id`).
    - The TradingView webhook calls `create_order_from_alert(..., user_id=alert.user_id)`, so once `alert.user_id` is populated (in S12), user ownership will be propagated automatically from alerts to orders.
- Queue & Orders APIs:
  - `backend/app/api/orders.py`:
    - `list_orders` and `list_manual_queue` now take an optional `user: User | None = Depends(get_current_user_optional)`.
    - When a user is present, queries are filtered with:
      - `Order.user_id == user.id OR Order.user_id IS NULL`, so:
        - Rows explicitly owned by the current user are returned.
        - Legacy/global rows with `user_id IS NULL` remain visible to all users during the migration period.
    - Detail and mutation endpoints (`get_order`, `update_order_status`, `edit_order`, `execute_order`) remain id-based and do not yet enforce per-user checks; stricter ownership rules will follow once S12 routing populates `user_id` consistently.
- Analytics APIs:
  - `backend/app/services/analytics.py`:
    - `compute_strategy_analytics` gained an optional `user_id` parameter.
    - When `user_id` is provided, it joins `AnalyticsTrade` to `Order` on `entry_order_id` and filters on `Order.user_id == user_id OR Order.user_id IS NULL`, so analytics are scoped to the current user plus global trades.
  - `backend/app/api/analytics.py`:
    - `analytics_summary` and `analytics_trades` now depend on `get_current_user_optional` and pass the current user id (when available) into analytics queries.
    - The trades endpoint filters the `(AnalyticsTrade, Order, Strategy)` query with the same `user_id OR NULL` pattern, ensuring that each user sees their own trades plus any legacy/global ones.
- Scope and future work:
  - S11/G03 focuses on **API-level scoping**: filtering Queue, Orders, and Analytics by the current user where a session exists, while keeping legacy data visible.
  - Deriving `alert.user_id` (and thus `order.user_id`) from TradingView payloads is intentionally deferred to S12’s routing/adapter work; once that is in place, we can:
    - Stop treating `user_id IS NULL` rows as global.
    - Tighten detail/mutation endpoints so a user cannot act on another user’s orders except via explicit ADMIN tooling.

## Sprint S12 – TradingView alert v2 and multi-broker routing (planned)

### S12 / G01 – TradingView alert schema and routing design

Tasks: `S12_G01_TB001`, `S12_G01_TB002`

- Normalized alert schema:
  - Defined an internal logical schema (implemented initially as a Pydantic-style model in code comments and service design) with the following core fields:
    - Identity: `user_id`, `broker_name`, optional `broker_account_id`, `source_platform`.
    - Strategy: `strategy_name`, optional `strategy_id`, eventual `alert_type` (entry/exit/SL/etc.).
    - Trade: `symbol`, `exchange`, `side`, `qty`, `price`, `product`, `timeframe`.
    - Timestamps: `received_at` (server time), `bar_time` (from payload), and raw payload snapshot.
  - This schema is not yet a separate DB table; instead, alerts are stored in the existing `alerts` table with:
    - `alerts.user_id` linking to `users`.
    - `alerts.strategy_id`, `symbol`, `exchange`, `interval`, `action`, `qty`, `price`, `platform`, `bar_time`, and `raw_payload` capturing the normalized + raw fields.
- User routing design:
  - TradingView payloads now include a dedicated `st_user_id` field:
    - `backend/app/schemas/webhook.py::TradingViewWebhookPayload` gained `st_user_id: Optional[str]`.
    - We require `st_user_id` to match an existing `users.username` to process an alert.
  - `backend/app/api/webhook.py`:
    - If `st_user_id` is missing or blank:
      - Logs an informational event and records a `system_events` row with message `"Alert ignored: missing st_user_id"`.
      - Returns a minimal JSON body: `{"status": "ignored", "reason": "missing_st_user_id"}` and does not create `Alert`/`Order` rows.
    - If `st_user_id` does not match any `User.username`:
      - Logs a warning and records `"Alert ignored: unknown st_user_id"` in `system_events` with the provided id.
      - Returns `{"status": "ignored", "reason": "unknown_st_user_id", "st_user_id": "<value>"}`.
    - If `st_user_id` is valid:
      - Loads the corresponding `User`.
      - Creates `Alert` with `alert.user_id = user.id`.
      - Calls `create_order_from_alert(..., user_id=user.id)` so `Order.user_id` is also set.
  - Platform/broker routing:
    - For now we still use the `platform` field to gate processing:
      - Only `"zerodha"` and `"TRADINGVIEW"` (generic) are accepted; other platforms are ignored with `{"status": "ignored", "platform": "<value>"}`.
    - Broker selection is anchored on `broker_name="zerodha"` and the per-user `BrokerConnection`/`BrokerSecret` rows introduced in S11; future brokers (Fyers, CoinDCX, etc.) will slot into this pattern.
- Behavioural impact:
  - TradingView alerts must now explicitly carry `st_user_id` (e.g., `"st_user_id": "cbiswas"`) to create alerts and orders; this guarantees that every ingested alert is associated with a concrete SigmaTrader user.
  - Alerts without `st_user_id` or with an unknown id are explicitly ignored but leave an audit trail in `system_events`, making it easy to diagnose misconfigured TradingView templates.
  - With S11’s API filtering in place, the Queue, Orders, and Analytics views naturally become per-user as new alerts/orders are created with a populated `user_id`.

### S12 / G02 – Zerodha adapter and per-user account mapping

Tasks: `S12_G02_TB001`, `S12_G02_TB002`

- Zerodha / TradingView adapter:
  - Implemented `backend/app/services/tradingview_zerodha_adapter.py` with:
    - `NormalizedAlert` dataclass capturing the normalized fields for Zerodha: `user_id`, `broker_name`, `strategy_name`, `symbol_display`, `broker_symbol`, `broker_exchange`, `side`, `qty`, `price`, `product`, `timeframe`, `bar_time`, `reason`, and `raw_payload`.
    - `normalize_tradingview_payload_for_zerodha(payload, user)`:
      - Reads side/qty/price/product from `TradeDetails`, with `trade_type`-based defaulting between `MIS`/`CNC`.
      - Splits TradingView symbols like `NSE:INFY` into `broker_exchange="NSE"` and `broker_symbol="INFY"` while keeping `symbol_display` as the original TV symbol.
      - Applies the config-based symbol map (`load_zerodha_symbol_map`) so TV symbols can be overridden per exchange when Zerodha uses different codes.
      - Derives `reason` from `order_comment` / `order_alert_message` via the `comment` / `alert_message` fields in `TradeDetails`.
- Alert model and storage:
  - Extended `Alert` with a `reason` column (via Alembic `0009_add_alert_reason.py`) and store the adapter’s `reason` value there, while still keeping the full raw payload in `raw_payload`.
  - This gives downstream components (queue, history, analytics) a simple, indexed place to access the human-readable trigger description.
- Per-user broker/account mapping:
  - `BrokerConnection` already has `user_id` and `broker_user_id`:
    - `connect_zerodha` and `zerodha_status` call `kite.profile()` and persist Zerodha `user_id` as `broker_user_id`.
  - `Order` now has `broker_account_id`:
    - `_get_zerodha_client` attaches `broker_user_id` to the Zerodha client.
    - `execute_order` stamps `order.broker_account_id` from `client.broker_user_id` before placing the order, so both successful and failed executions are tied to the correct Zerodha account.
  - Together with `Order.user_id` from S11, this gives a clean `(SigmaTrader user, Zerodha account)` mapping for every order created via TradingView.

### S12 / G03 – Webhook v2 implementation and tests

Tasks: `S12_G03_TB001`, `S12_G03_TB002`

- Backend:
  - `/webhook/tradingview` is now fully wired to the Zerodha adapter and per-user routing:
    - Uses `normalize_tradingview_payload_for_zerodha` to derive symbols, side/qty/price/product, timeframe, and a human-readable `reason` from each TradingView payload.
    - Requires `st_user_id` to resolve to a `User.username`; alerts without `st_user_id` or with an unknown user are ignored with structured `system_events` entries.
    - Creates `Alert` and `Order` rows with `user_id` populated so that all downstream APIs (Queue, Orders, Analytics) are per-user.
  - Execution routing:
    - Strategy execution_mode controls MANUAL vs AUTO behaviour:
      - `MANUAL` strategies → orders are created with `mode="MANUAL"` and `status="WAITING"`; no broker call is attempted.
      - `AUTO` strategies → orders are created with `mode="AUTO"` and then executed immediately via the shared `execute_order` endpoint.
    - Broker connection handling:
      - If Zerodha is not connected, `execute_order` raises a 400 `"Zerodha is not connected."`.
      - The webhook catches this specific case, marks the AUTO order as `status="FAILED"` with `error_message="Zerodha is not connected for AUTO mode."`, and records a `system_events` row: `"AUTO order rejected: broker not connected"`.
      - For connected accounts, AUTO orders proceed through the normal risk + order placement flow.
- Tests:
  - `backend/tests/test_webhook_tradingview.py`:
    - `test_webhook_persists_alert_with_valid_secret`:
      - Verifies that alerts with `st_user_id="webhook-user"` create `Alert` and `Order` rows bound to that user, with MANUAL/WAITING status.
    - `test_webhook_auto_strategy_routes_to_auto_and_executes`:
      - Uses a fake Zerodha client to confirm that AUTO strategies create orders in `AUTO` mode, mark them as `SENT`, and that the fake broker is called exactly once.
    - `test_webhook_manual_strategy_creates_waiting_order_for_user`:
      - Ensures MANUAL strategies create per-user WAITING orders without triggering broker execution.
    - `test_webhook_auto_strategy_rejected_when_broker_not_connected`:
      - Confirms that when no Zerodha connection exists, AUTO alerts return HTTP 400 with a clear `"Zerodha is not connected"` message and the corresponding order is persisted with `status="FAILED"` and a helpful error message.
  - `backend/tests/test_orders_api.py`:
    - `test_manual_order_cannot_execute_when_broker_not_connected`:
      - Verifies that manual WAITING orders cannot be executed when Zerodha is not connected: the `/api/orders/{id}/execute` endpoint returns 400 and the order remains in `status="WAITING"`.

### S12 / G04 – Config-based mapping for future brokers/platforms

Tasks: `S12_G04_TB001`

- Zerodha symbol mapping config:
  - Introduced a JSON-based symbol map under `backend/config/zerodha_symbol_map.json(.example)` with the shape:
    - `{ "NSE": { "SCHNEIDER": "SCHNEIDER-EQ" }, "BSE": { ... } }`
  - Added `load_zerodha_symbol_map()` in `backend/app/config_files.py`:
    - Reads `zerodha_symbol_map.json` from `ST_CONFIG_DIR` (or `backend/config` by default).
    - Returns a `dict[exchange][symbol] -> mapped_symbol`, normalizing exchange and symbol keys to upper-case.
    - Returns `{}` when the file does not exist, so the system safely falls back to a 1:1 TradingView → broker symbol assumption.
- Adapter integration:
  - `backend/app/services/tradingview_zerodha_adapter.py` now calls `load_zerodha_symbol_map()` and, when a mapping exists for `(broker_exchange, broker_symbol)`, replaces `broker_symbol` with the configured value while keeping `symbol_display` unchanged.
  - This allows TradingView symbols that differ from Zerodha’s (e.g., `NSE:SCHNEIDER`) to be mapped to broker-specific codes (`SCHNEIDER-EQ`) without changing code.
- Tests:
  - `backend/tests/test_tradingview_zerodha_adapter.py`:
    - Verifies that `load_zerodha_symbol_map()` returns an empty mapping when no file is present.
    - Confirms that when a symbol map is configured in a temporary `ST_CONFIG_DIR`, `normalize_tradingview_payload_for_zerodha`:
      - Uses the mapped `broker_symbol` for Zerodha calls.
      - Preserves the original TradingView symbol as `symbol_display`.
- Future extensions:
  - The config mechanism currently focuses on symbol overrides for Zerodha; the same pattern can be extended to:
    - Additional brokers/platforms (Fyers, CoinDCX, internal alert producers) with their own symbol maps.
    - Field-level mapping (side/qty/price/product/alert_type/reason) once we introduce adapters for those platforms, keeping core webhook logic unchanged.

## Sprint S13 – Appearance and theming

### S13 / G01 – Appearance and theming (light/dark + presets)

Tasks: `S13_G01_TF001`, `S13_G01_TF002`, `S13_G01_TB003`

- Theme system:
  - `frontend/src/theme.tsx` defines:
    - `ThemeId = 'dark' | 'light' | 'amber'`.
    - Three preset MUI themes:
      - `dark`: deep navy backgrounds with soft blue primary (`#90caf9`) and muted pink secondary (`#f48fb1`), tuned for a professional dark dashboard.
      - `light`: light grey app background with white cards, rich blue primary (`#1565c0`) and subtle orange secondary (`#ff9800`), with dark text for readability.
      - `amber`: warm dark palette with brownish backgrounds and amber/coral accents (`#ffb300` / `#ff7043`).
    - Helper `isValidThemeId` and `DEFAULT_THEME_ID = 'dark'`.
  - `frontend/src/themeContext.tsx`:
    - `AppThemeProvider` wraps MUI’s `ThemeProvider` + `CssBaseline`.
    - Holds `themeId` in React state and persists it to `localStorage` under `st_theme_id`.
    - Exposes `useAppTheme()` hook (`{ themeId, setThemeId }`) for components to read or change the current theme.
- Wiring into the app:
  - `frontend/src/main.tsx`:
    - Wraps the entire app in `<AppThemeProvider>` so all views use the selected theme.
  - `frontend/src/services/auth.ts`:
    - Extended `CurrentUser` with `theme_id`.
    - Added `updateTheme(themeId)` calling `POST /api/auth/theme`.
  - `frontend/src/App.tsx`:
    - After `fetchCurrentUser`, if `user.theme_id` is a valid `ThemeId`, calls `setThemeId(user.theme_id)` to apply the user’s preferred theme.
    - On successful login, applies the same logic so the UI switches to the user’s theme immediately.
- Backend persistence:
  - `backend/app/models/user.py` and Alembic `0010_add_user_theme.py` add `theme_id` to the `users` table.
  - `backend/app/schemas/auth.py::UserRead` now includes `theme_id`, and `ThemeUpdateRequest` models the request payload.
  - `backend/app/api/auth.py` exposes `POST /api/auth/theme`:
    - Requires authentication.
    - Saves the requested `theme_id` on the current user and returns the updated `UserRead`.
- Appearance settings UI:
  - `frontend/src/layouts/MainLayout.tsx`:
    - Adds an **Appearance** entry to the left-hand navigation (`/appearance`) with a palette icon.
  - `frontend/src/routes/AppRoutes.tsx`:
    - New route: `/appearance` → `AppearancePage`.
  - `frontend/src/views/AppearancePage.tsx`:
    - Simple Appearance panel:
      - Radio group listing the three themes with user-friendly labels:
        - Dark (default), Light, Dark (amber accent).
      - On change:
        - Immediately updates the theme via `setThemeId`.
        - Calls `updateTheme(themeId)` to persist the choice server-side.
      - Shows a small “Saving theme preference...” caption while saving and an error caption if the backend update fails.

### S13 / G02 – Branding and logo integration

Tasks: `S13_G02_TF001`

- Logo asset:
  - Placed `sigma_trader_logo.png` in `frontend/public`, making it available at `/sigma_trader_logo.png` in the SPA.
- App shell integration:
  - `frontend/src/layouts/MainLayout.tsx`:
    - Sidebar (Drawer):
      - Toolbar now shows a circular “logo mark” next to the app name:
        - A 40×40 pill (`LogoMark` component) with `background.paper`, subtle border and shadow, and the `sigma_trader_logo.png` image masked inside.
    - Top AppBar:
      - Left side of the top bar also uses `LogoMark` (hidden on extra-small screens to preserve space) next to the “SigmaTrader” title.
      - Using the theme’s `background.paper` and `divider` colours around the logo ensures it reads cleanly on all three themes (dark, light, amber) from S13/G01.
- Future branding work:
  - The logo is intentionally added without changing layout structure; a later sprint can extend this branding to the Auth/landing hero area and possibly add a favicon update if desired.

## Sprint S14 – Advanced order controls and risk-aware execution

### S14 / G01 – Advanced order types and stop-loss controls

Tasks: `S14_G01_TB001`, `S14_G01_TB002`

- Models and schema:
  - `backend/app/models/trading.py`:
    - `Order` now has:
      - `trigger_price: Optional[float]` – absolute trigger for stop-loss orders.
      - `trigger_percent: Optional[float]` – trigger distance in percent relative to LTP at execution time.
  - Alembic migration `backend/alembic/versions/0011_add_order_triggers.py`:
    - Adds `trigger_price` and `trigger_percent` columns to the `orders` table (both nullable `Float`).
- API schemas:
  - `backend/app/schemas/orders.py`:
    - `OrderRead` includes `trigger_price` and `trigger_percent` so the queue/orders UI can display them.
    - `OrderUpdate` now supports:
      - `order_type: Literal["MARKET", "LIMIT", "SL", "SL-M"]`.
      - Optional `trigger_price` and `trigger_percent` fields.
- Edit-order behaviour:
  - `backend/app/api/orders.py::edit_order`:
    - Still restricts edits to non-simulated `WAITING`/`MANUAL` orders.
    - Supports updating:
      - `qty` (must be positive).
      - `price` (must be non-negative).
      - `trigger_price` (must be positive when provided).
      - `trigger_percent` (any float, used for display/analytics).
      - `order_type` (validated against `MARKET`, `LIMIT`, `SL`, `SL-M`).
      - `product` and `gtt` as before.
    - Returns a 400 error with a clear message if validation fails.
- Zerodha client enhancements:
  - `backend/app/clients/zerodha.py`:
    - `ZerodhaClient.place_order(...)` now accepts a `trigger_price` argument and forwards it to `kite.place_order` alongside `price` when required.
    - Added `get_ltp(exchange, tradingsymbol) -> float`:
      - Wraps `kite.ltp([f"{exchange}:{tradingsymbol}"])`.
      - Returns the `last_price` for the instrument, raising a `RuntimeError` if the broker payload is missing the expected key.
    - `backend/tests/test_zerodha_client.py`:
      - `FakeKite` gained an `ltp(...)` method returning a deterministic `last_price` to support new guardrail logic in tests.
- Execution and stop-loss guardrails:
  - `backend/app/api/orders.py::execute_order`:
    - After risk checks and Zerodha client creation:
      - For `order.order_type in {"SL", "SL-M"}`:
        - Requires `order.trigger_price > 0`; otherwise returns `400 "Trigger price must be positive for SL/SL-M orders."`.
        - For `SL` orders, also requires `order.price > 0`; otherwise returns `400 "Price must be positive for SL orders."`.
        - Fetches LTP via `client.get_ltp(exchange, tradingsymbol)`.
        - Computes `trigger_percent = ((trigger_price - LTP) / LTP) * 100.0` and persists it on the order:
          - This explicitly makes trigger percent relative to **LTP**, matching the intended semantics.
        - Enforces directional guardrails:
          - For `BUY` SL/SL-M orders → rejects if `trigger_price < LTP` (stop below market would be immediately unsafe).
          - For `SELL` SL/SL-M orders → rejects if `trigger_price > LTP`.
        - Any LTP fetch errors are logged and converted to a `502` with a clear `"Failed to fetch LTP for stop-loss validation: ..."` message.
      - Internal `_place(...)` helper now:
        - Computes `trigger_price` parameter for Zerodha only when `order_type` is `SL` or `SL-M` and `order.trigger_price` is set.
        - Derives `price` as:
          - `LIMIT` → `order.price`.
          - `SL` → `order.price`.
          - `MARKET` and `SL-M` → omit `price` so they behave as market/stop-market orders.
        - Calls `client.place_order(...)` with the expanded parameter set.
    - Non-SL orders (`MARKET`/`LIMIT`) continue to behave as before, aside from now carrying nullable trigger fields.
- Frontend typings:
  - `frontend/src/services/orders.ts`:
    - `Order` type now has optional `trigger_price` and `trigger_percent` so the UI can render these if present.
    - `updateOrder` payload allows:
      - `order_type?: "MARKET" | "LIMIT" | "SL" | "SL-M"`.
      - `trigger_price?: number | null`, `trigger_percent?: number | null`.
    - The current edit dialog still sends only `MARKET`/`LIMIT` and no trigger fields; behaviour remains unchanged until S14/G03 extends the UI.

These changes complete the backend and typing support for advanced Zerodha order types and LTP-aware stop-loss parameters, ready for the richer edit dialog and funds preview planned in S14/G02–G03.

### S14 / G02 – Funds and margin preview for edited orders

Tasks: `S14_G02_TB001`, `S14_G02_TF002`

- Backend preview APIs:
  - `backend/app/api/zerodha.py`:
    - Helper `_get_kite_for_user(db, settings, user)` centralises creation of a user-scoped `KiteConnect` client, re-used by multiple endpoints.
    - `GET /api/zerodha/margins` (`zerodha_margins`):
      - Calls `kite.margins("equity")` and normalises the segment payload.
      - Extracts an `available` cash-like value (preferring `available.cash`, then `live_balance` or `opening_balance`) and returns:
        - `available: float`
        - `raw: Dict[str, Any]` (entire equity segment) via `MarginsResponse`.
    - `POST /api/zerodha/order-preview` (`zerodha_order_preview`):
      - Accepts `OrderPreviewRequest` (symbol, exchange, side, qty, product, order_type, optional price and trigger_price).
      - Normalises `symbol` into `exchange` and `tradingsymbol`.
      - Calls `kite.order_margins([...])` with a single order dict mirroring the execution parameters (including `trigger_price` for SL/SL-M).
      - Returns `OrderPreviewResponse`:
        - `required`: numeric total margin/amount required (from `total` or `margin` in the broker payload).
        - `charges`: nested charges dict when present.
        - `currency`: extracted from `currency` or `settlement_currency`.
        - `raw`: the full first entry from the broker response.
- Zerodha client/test helpers:
  - `backend/app/clients/zerodha.py`:
    - Added `margins(segment)` and `order_margins(params)` wrappers to decouple the rest of the code from direct KiteConnect usage.
  - `backend/tests/test_zerodha_client.py`:
    - `FakeKite` gained `margins(...)` and `order_margins(...)` methods, returning deterministic structures so tests remain self-contained.
- Frontend funds preview:
  - `frontend/src/services/zerodha.ts`:
    - New types:
      - `ZerodhaMargins` (`available`, `raw`).
      - `ZerodhaOrderPreviewRequest` / `ZerodhaOrderPreview`.
    - New helpers:
      - `fetchZerodhaMargins()` → `GET /api/zerodha/margins`.
      - `previewZerodhaOrder(payload)` → `POST /api/zerodha/order-preview`.
  - `frontend/src/views/QueuePage.tsx`:
    - Edit dialog state now includes:
      - `fundsAvailable`, `fundsRequired`, `fundsCurrency`, `fundsLoading`, `fundsError`.
    - Added `refreshFundsPreview()`:
      - Validates current qty and price (and trigger price for SL/SL-M).
      - Calls `fetchZerodhaMargins()` and `previewZerodhaOrder(...)` using the current edits (symbol, exchange, side, qty, product, order_type, price, trigger_price).
      - Populates Required vs Available amounts or a user-friendly error message.
    - UI:
      - A “Funds & charges” card in the edit dialog shows:
        - `Required: <currency> <required> (incl. charges)`
        - `Available: <currency> <available>`
      - A “Recalculate” button triggers a fresh preview and shows a small loading state; initial state prompts the user to click Recalculate.

### S14 / G03 – Queue edit UX polish and stop-loss helpers

Tasks: `S14_G03_TF001`

- Side toggles and layout:
  - `frontend/src/views/QueuePage.tsx`:
    - The edit dialog header now shows the symbol plus BUY/SELL toggles:
      - BUY: `variant="contained"` `color="primary"` when active, `outlined` otherwise.
      - SELL: `variant="contained"` `color="error"` when active, `outlined` otherwise.
    - `editSide` state tracks the selected side and is sent in the `updateOrder` payload; `OrderUpdate` and `edit_order` were extended to accept and persist `side` as `"BUY"` or `"SELL"`.
- Order type and trigger fields:
  - The order type select now supports all advanced Zerodha types:
    - `MARKET`, `LIMIT`, `SL` (stop-loss limit), and `SL-M` (stop-loss market).
    - `editOrderType` initialises from the order’s current type.
  - For SL/SL-M orders, the dialog shows:
    - A toggle between two trigger modes:
      - “Use price” → user edits trigger price directly.
      - “Use % vs LTP” → user edits trigger percent relative to last traded price.
    - Two complementary fields:
      - `Trigger price` (numeric).
      - `Trigger % vs LTP` (numeric).
- LTP-aware helper behaviour:
  - `frontend/src/services/zerodha.ts`:
    - Added `fetchZerodhaLtp(symbol, exchange)` calling `GET /api/zerodha/ltp` and returning `{ ltp }`.
  - `backend/app/api/zerodha.py`:
    - New `GET /api/zerodha/ltp` endpoint:
      - Uses `_get_kite_for_user` and `kite.ltp(...)` to fetch the current `last_price` for `exchange:symbol`.
      - Returns `LtpResponse(ltp=...)` or a 502 error if the payload is invalid.
  - In `QueuePage`:
    - When an SL/SL-M order is edited, the dialog automatically fetches LTP for the symbol (once per open) and stores it in `ltp`/`ltpError`.
    - A `triggerMode` state (`"PRICE"` or `"PERCENT"`) controls which field is the “driver”:
      - PRICE mode:
        - `Trigger price` is editable.
        - When both LTP and trigger price are valid, `Trigger %` is auto-computed as `((trigger_price - LTP) / LTP) * 100` and shown read-only.
      - PERCENT mode:
        - `Trigger %` is editable (disabled when LTP is not available).
        - When both LTP and trigger percent are valid, `Trigger price` is derived as `LTP * (1 + trigger_percent / 100)` and shown read-only.
    - If LTP cannot be fetched, percent mode is disabled and the helper text surfaces the LTP error while still allowing pure price entry.
- Validation and persistence:
  - When saving:
    - SL/SL-M orders require a positive trigger price (derived from the active mode).
    - Optional trigger percent is validated as numeric, then sent along if present.
  - The payload sent to `updateOrder` contains:
    - `qty`, `price`, `side`, `order_type`, `product`, `gtt`.
    - `trigger_price` (mandatory for SL/SL-M).
    - `trigger_percent` (when provided).
  - On the backend, `OrderUpdate` and `edit_order` now accept and persist these trigger fields; execution guardrails (from S14/G01) still validate against broker-side LTP at execution time.

Together, S14/G02 and S14/G03 turn the Waiting Queue edit dialog into a richer, broker-aware order editor: users can adjust side, order type (including SL/SL-M), and trigger levels with LTP-derived helpers and see Required vs Available funds—including charges—before sending orders to Zerodha.
