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
