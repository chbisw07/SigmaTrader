# tvapp – Incremental Sprint Plan

This document defines phased, incremental sprints for implementing the tvapp (TradingView → App → Zerodha) system.  
Each sprint produces a usable MVP slice, building on previous sprints.

---

## Sprint Overview

| sprint# | description | details | user validations | user sign-off note |
|--------|-------------|---------|------------------|--------------------|
| S01 | Project setup & scaffolding | Set up the basic repo structure, backend (FastAPI), frontend (React+TS+MUI), and shared tooling. No trading logic yet, but app “skeleton” is running end-to-end. This is the foundation for all future work. | User can clone repo, run backend and frontend, see a basic UI layout with a top bar/sidebar, and verify the frontend calls the backend `/health` endpoint and shows “OK/Connected”. | “I can run the project locally, see the base UI, and the backend health check works. The foundation feels clean and maintainable.” |
| S02 | Core DB & domain model | Design and implement the SQLite schema (alerts, orders, strategies, risk_settings, etc.) and ORM layer. Provide basic admin APIs and a minimal UI to inspect strategies/risk settings. This sprint gives us a persistent backbone. | User can hit APIs (or use a small admin UI) to create/list strategies and their risk settings. User can inspect the SQLite DB and see the tables created correctly. | “The data model matches what we discussed in the PRD, and I can configure strategies/risk settings via API or UI. I’m happy with the schema for the next stages.” |
| S03 | TradingView webhook & manual queue backend | Implement the TradingView webhook endpoint, validate alerts, map to internal Alert entities, and create Orders in a WAITING state (manual queue). No broker integration yet. This sprint ensures the alert ingestion pipeline is correct and persisted. | User can configure TradingView webhook to call `/webhook/tradingview` with the sample JSON, then see alerts and corresponding WAITING orders appear in the DB or via backend API. | “Alerts from TradingView are arriving, being stored correctly, and converted into ‘waiting’ orders. The app is now reliably ingesting signals.” |
| S04 | Manual queue frontend & basic orders UI | Build the Waiting Queue and Orders History UI. Allow inline editing of orders in the queue (qty/price/type/product) and cancel/execute actions (execute only updates state for now, still no real broker). This sprint makes manual review very tangible. | User can open the web app, go to “Queue” and “Orders” pages, see incoming orders from alerts, edit them inline, click Execute/Cancel, and see the status change in the UI and DB. | “I can see and manage my manual queue visually. The UI matches my mental model of how orders should be reviewed before execution.” |
| S05 | Zerodha integration & execution from queue | Integrate Zerodha Kite Connect on the backend. Implement the “Connect Zerodha” flow, store tokens securely, and send orders from the manual queue to Zerodha. Handle basic success/failure and show results in the UI. This is the first real-money MVP. | User can connect to Zerodha, see the connection status, execute an order from the Waiting Queue, and then verify in Zerodha that an order was placed. UI shows Zerodha order ID and error messages when things fail. | “The app can place real orders in Zerodha from the manual queue, and I clearly see if they succeeded or failed. This is a usable first version for careful manual trading.” |
| S06 | Execution modes & risk management v1 | Implement AUTO vs MANUAL execution per strategy. Introduce real Risk Engine rules (max quantity, max order value, daily loss limits, short-sell protections, etc.) and apply them to both auto and manual executions. This sprint makes the system safer and more automated. | User can configure a strategy’s mode (AUTO/MANUAL), send alerts from TradingView, and see: AUTO → directly sent to Zerodha (if within risk limits); MANUAL → lands in queue. Risk constraints trigger visible adjustments/rejections with clear explanations. | “Strategies behave as AUTO or MANUAL as configured. Risk checks are working and visible. I feel safer letting some strategies run in AUTO.” |
| S07 | Status sync, positions & analytics MVP | Implement background sync with Zerodha for order status. Fetch and show positions/holdings. Implement trade grouping and basic analytics (P&L, win-rate, etc.) with charts and tables. This sprint turns the app into a real trading companion. | User can see order statuses updating to COMPLETE/REJECTED/etc., view positions and holdings in the app, and open an Analytics page that shows P&L and basic performance metrics per strategy and period. | “I can monitor my trades, see positions, and get a basic understanding of how each strategy performs. The app gives me useful trading insights.” |
| S08 | Hardening, logging, security & deployment | Add structured logging, robust error handling, security hardening, and Docker-based deployment. Add minimal log/notification UI and improve docs (runbook & deployment). After this sprint, the system is production-ready for personal use. | User can see meaningful logs/errors correlated to orders and alerts, run the system via Docker (or equivalent), and feel confident about security (secrets, auth, HTTPS). Documentation is sufficient to reinstall/deploy. | “The system feels stable, observable, and properly documented. I can deploy and maintain it without surprises.” |

---

## Sprint Details

### Sprint S01 – Project Setup & Scaffolding

**High-level goal**  
Create a clean, maintainable foundation for the project: backend (FastAPI), frontend (React+TS+MUI), and shared tooling (linting, formatting, basic docs). No domain logic yet.

**Details**  
- Set up backend repo structure (`src/app`, `tests`, config modules).
- Implement base FastAPI app with `/` and `/health` endpoints.
- Configure environment-based settings (dev/prod) so we can later plug in secrets and DB configs cleanly.
- Create frontend React app in TypeScript, add Material UI, routing, and a base layout with top bar and sidebar.
- Wire a simple API call from frontend to backend `/health` and display connection status.
- Add tooling: Git, pre-commit hooks, linters/formatters (black, isort/ruff, ESLint, Prettier).
- Write an initial README explaining how to run backend and frontend.

This sprint is the foundation: all subsequent domain features plug into this structure.

**User validations**  
- Able to clone the repo and follow the README to start backend and frontend.
- Visiting the app in the browser shows a basic layout with nav items.
- The UI shows backend health status (e.g. “API: Connected”).
- No trading features yet, but the structure feels clean and understandable.

**User sign-off note**  
> I can run the app locally and see the base UI and API health. The structure and tooling are acceptable as the foundation for further development.

---

### Sprint S02 – Core DB & Domain Model

**High-level goal**  
Design and implement the SQLite schema and ORM models for core entities (alerts, orders, strategies, risk_settings, etc.). Provide basic APIs and minimal admin UI to inspect configurations.

**Details**  
- Design tables:
  - `strategies`, `alerts`, `orders`, `risk_settings`, plus early scaffolding for `positions` and `analytics_trades`.
- Implement SQLAlchemy models and DB session management in FastAPI.
- Set up Alembic (or similar) for DB migrations.
- Implement backend APIs for:
  - Listing/creating/updating strategies.
  - Listing/creating/updating risk settings (global + per-strategy).
- Add a simple read-only admin view in the frontend to display existing strategies and risk settings.

This sprint provides the persistent backbone that S03+ rely on for alert ingestion and order management.

**User validations**  
- DB file (`sqlite`) is created with the agreed tables.
- User can use an API client or simple UI to:
  - Create strategies and risk settings.
  - List them and see that they persist across app restarts.
- Schema aligns with the PRD (supports WAITING orders, risk config, analytics later).

**User sign-off note**  
> The DB schema and basic admin interfaces match my expectations. I’m comfortable building the rest of the system on top of this model.

---

### Sprint S03 – TradingView Webhook & Manual Queue Backend

**High-level goal**  
Build the full alert ingestion pipeline from TradingView to DB and orders in `WAITING` state (manual queue). No broker yet.

**Details**  
- Implement `/webhook/tradingview` endpoint:
  - Validate JSON payload and secret key.
  - Map alert fields into internal `Alert` entity.
  - Associate with strategy (based on `strategy_name`).
- Convert alerts into `Order` entities:
  - Default `mode = MANUAL` and `status = WAITING`.
  - Store required details: side, qty, price, product placeholder.
- Expose backend APIs:
  - List WAITING orders with filters.
  - Fetch basic alert/order information for UI.
- Introduce a Risk Engine interface with stub implementation:
  - For now, only logs checks and decisions.
  - Will be expanded in S06.

This sprint guarantees that alerts reliably become pending orders in our system.

**User validations**  
- Configure TradingView to send alerts to the app, with the sample JSON including `secret`.
- When alerts fire, user can query the backend and see:
  - Records in `alerts` table.
  - Corresponding orders in `orders` table with `WAITING` status.
- No Zerodha traffic yet (safe to test with dummy data).

**User sign-off note**  
> TradingView alerts are consistently received, validated, and turned into WAITING orders. The data looks correct and traceable from alert → order.

---

### Sprint S04 – Manual Queue Frontend & Orders UI

**High-level goal**  
Provide a user-friendly UI for the manual queue and orders list. Allow editing and cancel/execute actions (execute only updates state locally for now).

**Details**  
- Implement navigation and page skeletons:
  - Dashboard, Queue, Orders, Analytics, Settings.
- Implement **Waiting Queue** page:
  - Material UI table listing WAITING orders.
  - Inline editing of qty, price, order type (MARKET/LIMIT), product (MIS/CNC).
  - Buttons: Execute, Cancel.
- Implement backend endpoints:
  - Update order details (when edited).
  - Cancel order (change status to `CANCELLED`).
  - Execute order (change status to e.g. `READY_TO_SEND` or `EXECUTED_LOCAL` just for this sprint).
- Implement **Orders History** page:
  - Table showing orders with filters (date, strategy, status, symbol).
  - Clicking a row optionally opens a details drawer with raw alert info later.

This sprint makes the manual review workflow tangible, even before connecting to Zerodha.

**User validations**  
- User sends sample alerts and sees them appear in the Queue frontend.
- User edits values in-place and sees DB values updated.
- User clicks Cancel/Execute and sees status changes reflected in both UI and DB.
- No actual broker calls yet; still sandbox behavior.

**User sign-off note**  
> I can visually manage my queued orders: edit them, cancel them, and mark them executed (locally). The screens reflect the flows I expect before we plug in Zerodha.

---

### Sprint S05 – Zerodha Integration & Execution from Queue

**High-level goal**  
Integrate Zerodha Kite Connect, implement “Connect Zerodha” flow, and actually place orders from the manual queue into Zerodha.

**Details**  
- Backend:
  - Configure Zerodha Kite Connect client using env vars for API key/secret.
  - Implement flow to exchange `request_token` → `access_token` and store it encrypted.
  - Implement service to place orders (market/limit, MIS/CNC).
  - Implement service to fetch order book and order status from Zerodha.
- Frontend:
  - “Connect Zerodha” button and simple connection status indicator.
  - Basic UI to show broker connection health on Dashboard/Settings.
- Queue execution integration:
  - On Execute:
    - Use current order values to call Zerodha.
    - Store Zerodha order ID in `orders` table.
    - Update status (e.g. `SENT` or `EXECUTED` depending on response).
  - On error:
    - Update status to `FAILED` with error message.
    - Surface error prominently in Queue and Orders pages.

Now the app is capable of true manual trading via Zerodha with order history recorded.

**User validations**  
- User completes Zerodha connection flow and sees status as “Connected”.
- From the Queue, executing an order:
  - Creates a real order visible in Zerodha’s platform.
  - Shows a Zerodha order ID and success state in the app.
- Executing orders with invalid parameters clearly fails with a readable error in the UI.

**User sign-off note**  
> The app successfully sends real orders to Zerodha from the manual queue, and I can see success/failure clearly. I’m comfortable using this for careful live trading.

---

### Sprint S06 – Execution Modes & Risk Management v1

**High-level goal**  
Turn on AUTO mode for strategies and implement real risk management rules. Make sure both AUTO and MANUAL modes are safe and predictable.

**Details**  
- Execution modes:
  - Extend `strategies` to store `execution_mode = AUTO|MANUAL`.
  - Implement alert routing:
    - AUTO → risk check → Zerodha (no manual queue).
    - MANUAL → risk check (later) + WAITING queue, as before.
  - Add UI for changing execution mode in Settings.
- Risk Engine v1:
  - Implement:
    - `max_order_value` (₹ limit).
    - `max_quantity_per_order`.
    - `allow_short_selling`.
    - Daily loss limits (based on realized PnL; open PnL approximations later).
  - Make Risk Engine run before any Zerodha call:
    - If violating hard limits → reject order (status `REJECTED_RISK`) with explanation.
    - If using “clamp” mode → adjust qty/value and record the adjustment reason.
  - Show risk decisions in UI:
    - e.g. tooltips or messages on orders indicating clamped/rejected.

This sprint is all about **safety** and **trust** in automation.

**User validations**  
- User sets a strategy to AUTO and sends alerts:
  - Orders within risk limits are automatically sent to Zerodha.
  - Orders exceeding limits are either reduced or rejected as configured, with explanations.
- User sets strict daily loss limit and verifies that once the limit is breached, further orders are blocked.
- Short-sell protection works as expected (e.g., CNC sell blocked without holdings, if configured).

**User sign-off note**  
> AUTO vs MANUAL works exactly as configured, and the risk rules are enforced in a transparent way. I trust the system more now, even in AUTO mode.

---

### Sprint S07 – Status Sync, Positions & Analytics MVP

**High-level goal**  
Turn the app into a complete trading companion by syncing order status, showing positions/holdings, and providing first-cut analytics.

**Details**  
- Status sync:
  - Implement background job (e.g., periodic task) to fetch order book from Zerodha and sync statuses (OPEN/COMPLETE/REJECTED/PARTIAL).
  - Update orders in DB with latest status and any rejection reasons.
- Positions & holdings:
  - Backend services to fetch positions and holdings, store/cache in DB.
  - API endpoints exposing positions/holdings.
  - Frontend pages:
    - Positions: symbol, qty, avg price, LTP, P&L.
    - Holdings: symbol, qty, avg price, current value, unrealized P&L.
- Analytics:
  - Trade grouping logic:
    - Pair entry/exit orders into trades and populate `analytics_trades`.
  - Backend analytics:
    - Compute P&L, win rate, average win/loss, max drawdown per strategy and date range.
  - Frontend analytics:
    - Summary cards for key metrics.
    - P&L over time chart.
    - P&L by symbol or strategy chart.
    - Trades table with filters.

After this sprint, the app is deeply informative, not just an execution pipe.

**User validations**  
- User runs some trades (even small size), then sees:
  - Order statuses in the app match Zerodha.
  - Positions and holdings in the app roughly match Zerodha’s view.
  - Analytics page shows P&L and basic stats that align with a manual sanity check.
- Filtering by strategy/date works as expected.

**User sign-off note**  
> I can monitor my portfolio and see meaningful performance analytics inside the app. The data aligns with Zerodha and with my expectations.

---

### Sprint S08 – Hardening, Logging, Security & Deployment

**High-level goal**  
Polish and harden the system: robust logging, error handling, security, and deployment. The goal is a “production-ready for personal use” release.

**Details**  
- Logging & error handling:
  - Implement structured logging for alerts, orders, broker calls, risk decisions.
  - Add correlation IDs to trace a single alert through its entire lifecycle.
  - Normalize error responses from backend.
  - Add a minimal “System Events / Errors” view in the UI (or at least surface serious errors visibly).
- Security & config:
  - Ensure use of HTTPS (where applicable), secure cookies/JWT, and secrets loaded from environment variables.
  - Double-check access control (even if it’s single-user) and protect sensitive endpoints.
- Deployment:
  - Create Dockerfiles for backend and frontend.
  - Add docker-compose for local orchestration (backend, frontend, maybe a reverse proxy).
  - Document deployment steps and an operational runbook (how to rotate tokens, what to do if Zerodha fails, etc.).
- Documentation:
  - Update README with:
    - Final architecture diagram summary.
    - Sprint summary.
    - How to run, test, and deploy.

This sprint is about making the app sustainable over time.

**User validations**  
- User can run the full system via Docker (or documented deployment method) with minimal commands.
- Logs are readable and helpful for debugging issues.
- Sensitive values are not hard-coded in the repo; they come from environment/config.
- Documentation is sufficient for reinstallation and redeployment without the author present.

**User sign-off note**  
> The app feels robust and supportable. I understand how to deploy, monitor, and troubleshoot it. I’m happy calling this v1 “production-ready” for my use.

---
