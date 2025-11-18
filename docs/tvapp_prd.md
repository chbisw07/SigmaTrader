Let’s turn this into a solid product spec.

Below is a **comprehensive PRD** for your TradingView → App → Zerodha Kite trading system, plus **ASCII wireframes** at the end so you can “see” the app before building it.

---

## 1. Product Overview

### 1.1 Vision

Build a **full-fledged trading companion app** that:

1. Receives **live TradingView alerts** via webhooks.
2. Translates them into **standardized, risk-controlled orders**.
3. Routes them to **Zerodha Kite** for execution, with:

   * **Auto mode** – fire & forget (within safety limits).
   * **Manual mode** – queued, reviewable, editable orders before execution.
4. Provides **trading analytics** so the user can evaluate strategies driven by TradingView alerts.

### 1.2 Primary Objectives

* Reliable, low-latency capture of alerts.
* Simple and safe execution into **Zerodha (Kite)**.
* Robust **risk management** and **execution transparency**.
* Intuitive **web app UI** (React + Material UI).
* Easy local setup and deployment.

---

## 2. Target Users & Personas

### 2.1 Personas

1. **Experienced Retail Trader (Core)**

   * Uses TradingView strategies and alerts.
   * Wants automation but is wary of fat-finger and over-leverage.
   * Needs clear visibility into what was executed and why.

2. **Systematic/Algo Enthusiast**

   * Runs multiple strategies, symbols, and timeframes.
   * Needs **fine control** over per-strategy settings, limits, and analytics.

3. **Cautious/Transitioning Trader**

   * Moves from manual to automated.
   * Uses **Manual Mode** heavily to build trust before going full auto.

---

## 3. High-Level Features

1. **TradingView Webhook Ingest**

   * Secure endpoint for JSON alerts (like your example).
   * Validation using `secret` key.
   * Conversion to internal “Order Request” entity.

2. **Execution Modes**

   * **Auto Mode**

     * Alerts → validated orders → Zerodha Kite order API.
   * **Manual Mode**

     * Alerts → validated orders → **Waiting Queue**.
     * User edits qty/price/type/trade_type/GTT conversion → execute.

3. **Waiting Queue (Manual Execution)**

   * List of pending orders.
   * In-place editing:

     * Quantity, price, order type (market/limit), product (MIS/CNC).
     * Optional “Convert to GTT”.
   * Buttons: **Execute**, **Cancel**.
   * Status updates: `PENDING`, `EDITED`, `SENT`, `FAILED`.

4. **Order History & Status Sync**

   * Store all app-side orders in SQLite with mapping to Zerodha order IDs.
   * Fetch status from Zerodha (polling or WebSocket).
   * Status states: `PENDING`, `OPEN`, `PARTIALLY_FILLED`, `COMPLETE`, `CANCELLED`, `REJECTED`.

5. **Risk Management Layer**

   * Global and per-strategy settings:

     * Max quantity per order.
     * Max capital per order.
     * Max daily loss (soft/hard stop).
     * Restrict **short selling** or enforce extra confirmations.
     * Instrument whitelist/blacklist.
   * “Risk override” logic:

     * When TradingView suggests something beyond constraints, system clamps or rejects with clear explanation.

6. **Connection to Zerodha Kite**

   * Simple **“Connect to Broker”** flow using Kite OAuth (via Python + FastAPI).
   * Store access tokens securely (encrypted at rest).
   * Reconnect/refresh token handling.

7. **Logging & Error Handling**

   * Structured logging for:

     * Incoming alerts.
     * Order transformation and validation.
     * Zerodha API requests/responses.
   * UI surfaces human-readable errors + correlation IDs.

8. **Trade Analytics**

   * Per strategy:

     * P&L, win-rate, avg R:R, max drawdown.
   * Filters by:

     * Date range, symbol, strategy, trade type.
   * Simple charts and tables (frontend).

9. **System Settings**

   * Execution mode per strategy (`AUTO` / `MANUAL`).
   * Default product type (MIS/CNC).
   * Default order type (MARKET/LIMIT).
   * Max slippage allowed for market → limit conversion, if you want.
   * Broker configuration & secrets:
     * Settings page shows supported brokers/platforms (initially Zerodha/Kite) as a selectable list.
     * For each broker, user can manage key/value credentials (e.g., `api_key`, `api_secret`) via a small editable table:
       * Two columns: **Key** and **Value**; rows are flexible so different platforms can define their own keys.
       * Secret values are stored encrypted at rest (using the app’s crypto key) and rendered as password fields with a “show/hide” toggle.
     * Zerodha request tokens are also captured via a masked field with optional reveal, and when connected the Settings view shows the Zerodha user id.

10. **Quality-of-Life Improvements (Recommended)**

    * **Simulation / Paper Mode**: Same logic, but orders are not sent to Zerodha; instead they are routed to a lightweight paper engine that uses price polling (LTP) to fill simulated orders within user-configured intervals.
    * **Strategy Routing**: Use `strategy_name` to route to different configs (different RM rules, modes).
    * **Notification Hooks**: Optional email/Telegram alerts when orders fail or hit risk limits.
    * **Health Panel**: Show TradingView webhook health, Zerodha connectivity status, and DB status.

---

## 4. System Architecture

### 4.1 High-Level Architecture

* **Frontend**

  * TypeScript + React + Material UI SPA.
  * Talks to FastAPI backend (JSON REST APIs).
  * Node.js is used as tooling (build, bundling), not runtime for business logic.

* **Backend**

  * **FastAPI (Python)**:

    * Exposes:

      * `/webhook/tradingview` (public, protected by secret).
      * Auth/session endpoints (for frontend).
      * Order queue, order history, risk settings, analytics.
    * Integrates with **Zerodha Kite Connect Python library**.
  * Background tasks (FastAPI / asyncio) for:

    * Sending orders to Kite.
    * Polling/streaming order status.
    * Risk monitoring (e.g., daily loss checks).

* **Database**

  * SQLite:

    * Tables: `alerts`, `orders`, `positions`, `holdings`, `strategies`, `risk_settings`, `analytics_cache`, `logs` (optional summarized logs).
    * Use SQLAlchemy or equivalent ORM.

* **Security**

  * API key between TradingView and backend (`secret`).
  * Session auth on frontend (JWT or secure cookie).
  * Encrypted storage of Zerodha tokens.

---

## 5. Detailed Functional Requirements

### 5.1 TradingView Webhook

**Input**: JSON as you specified.

**Backend Behavior:**

1. Validate:

   * `secret` matches configured key.
   * Required fields present (`platform`, `trade_details.order_action`, etc.).
2. Normalize into internal `Alert` entity:

   * `id`, `strategy_name`, `symbol`, `exchange`, `timeframe`, `direction`, `size`, `price`, `timestamp`, raw payload.
3. Determine **strategy config**:

   * Look up `strategy_name` in `strategies` table for:

     * Execution mode.
     * Risk overrides.
4. Convert to internal **Order Request** entity.
5. Persist to DB.
6. Route:

   * If `AUTO` → run Risk Engine → if pass → create **Order** and send to Zerodha.
   * If `MANUAL` → create **Order** with `status = WAITING` (queued).

**Error Cases:**

* Invalid secret → 401.
* Malformed JSON → 400.
* Strategy not configured → default to `MANUAL` and log warning.

### 5.2 Order Lifecycle

**States (App-side):**

* `WAITING` (Manual queue)
* `VALIDATED`
* `SENDING`
* `SENT`
* `FAILED`
* `EXECUTED` (maps to Zerodha `COMPLETE`)
* `PARTIALLY_EXECUTED`
* `CANCELLED`
* `REJECTED` (from broker)

**Auto Mode Flow:**

1. Alert → Order Request.
2. Risk Engine applies limits.
3. If rejected → Order with `REJECTED`, show reason in UI.
4. If accepted → send to Zerodha → `SENDING`.
5. On success:

   * Save Zerodha order ID.
   * Status `SENT`.
6. Background job updates status to `OPEN`/`COMPLETE` etc. using broker status stream/poll.
7. Frontend polls/subscribes to status changes.

**Manual Mode Flow:**

1. Alert → Order Request → `WAITING`.
2. User opens **Waiting Queue**.
3. User edits:

   * Quantity.
   * Price.
   * Order type (MARKET/LIMIT).
   * Product (MIS/CNC).
   * “Convert to GTT” toggle if applicable.
4. On “Execute”:

   * Risk Engine re-checks with new values.
   * If OK → send to Zerodha, follow same flow as auto.
5. On “Cancel”:

   * Status `CANCELLED`, removed from active queue but stored.

### 5.3 Risk Management

**Configurable per Strategy + Global Defaults:**

* `max_order_value` (₹).
* `max_quantity_per_order`.
* `max_daily_loss` (sum of realized + open PnL).
* `allow_short_selling` (bool).
* `max_open_positions`.
* `symbol_whitelist` / `symbol_blacklist`.

**Behavior:**

* Every order (auto or manual) passes through RM:

  * If `order_value > max_order_value` → clamp to max or reject (configurable).
  * If `order_qty > max_quantity_per_order` → clamp or reject.
  * If daily loss beyond threshold → reject and mark “Daily loss limit reached”.
  * If order is SELL and user has insufficient holdings (for CNC) → require extra confirmation or reject (depending on configuration).
* RM decisions must be logged and visible in UI (e.g., “Quantity reduced from 500 to 200 due to risk limits”).

### 5.4 Zerodha Kite Integration

**Requirements:**

* Use official Python client.
* Store:

  * `api_key`, `api_secret` in env/config.
  * `access_token` in DB (encrypted).
* Features:

  * Place orders (market/limit, MIS/CNC).
  * Fetch order book & trade book.
  * Fetch positions & holdings.
  * Fetch status of a given order ID.

**UX Flow:**

1. User clicks **“Connect Zerodha”**.
2. App opens Kite OAuth URL.
3. After login, user copies `request_token` back (or redirect to FastAPI callback).
4. Backend exchanges `request_token` → `access_token`.
5. Save and show **“Connected to Zerodha”** with last sync time.

---

## 6. Data Model (SQLite – High Level)

### 6.1 Tables (Simplified)

* `users`

  * `id`, `email`, `password_hash`, `created_at`.
* `strategies`

  * `id`, `name`, `execution_mode`, `risk_settings_id`, `enabled`.
* `alerts`

  * `id`, `raw_payload`, `strategy_id`, `symbol`, `exchange`,
  * `interval`, `action` (BUY/SELL), `contracts`, `price`,
  * `received_at`, `bar_time`, `platform`.
* `orders`

  * `id`, `alert_id`, `strategy_id`, `symbol`, `exchange`,
  * `side` (BUY/SELL), `qty`, `price`, `order_type`, `product`,
  * `gtt` (bool), `status`, `zerodha_order_id`, `error_message`,
  * `created_at`, `updated_at`, `mode` (AUTO/MANUAL), `simulated` (bool).
* `risk_settings`

  * Fields for limits described above.
* `positions`

  * `id`, `symbol`, `product`, `qty`, `avg_price`, `pnl`, `last_updated`.
* `analytics_trades`

  * For PnL calculations: `entry_order_id`, `exit_order_id`, `strategy_id`, `pnl`, `r_multiple`, timestamps.
* `settings`

  * Global config: `key`, `value`.

---

## 7. Frontend UX / UI

### 7.1 General UI Aesthetics

* **Material UI** theme:

  * Dark mode by default (trader-friendly).
  * Accent color for BUY (green) and SELL (red).
  * Clean typography, high contrast for tables.
* Layout:

  * Left sidebar navigation.
  * Top bar showing **connection status**, **current mode**, **user info**.

### 7.2 Screens

1. **Login / Setup**

   * Minimal login for local use (optional).
   * CTA to **Connect Zerodha**.

2. **Dashboard**

   * Top widgets:

     * Today’s P&L (realized + open).
     * Number of executed trades today.
     * Active strategies & their mode (AUTO/MANUAL).
     * Zerodha connection status + last sync.
   * Chart:

     * Equity curve for selected date range.
   * Recent activity feed:

     * “Alert received”, “Order executed”, “Order rejected”.

3. **Waiting Queue (Manual Orders)**

   * Table:

     * Columns: Strategy | Symbol | Side | Qty | Price | Order Type | Product | Mode | Received At | Actions.
   * Actions:

     * Inline edit on Qty/Price/Type/Product.
     * Buttons: **Execute**, **Cancel**.
   * Bulk actions (optional later): Execute selected, Cancel selected.

4. **Order History**

   * Filters:

     * Date range, Strategy, Symbol, Status.
   * Table:

     * Strategy | Symbol | Side | Qty | Price | Status | Zerodha Order ID | P&L (if closed).
   * Click row → details drawer with:

     * Raw alert JSON.
     * Broker response logs.
     * Risk adjustments performed.

5. **Positions & Holdings**

   * Positions table:

     * Symbol | Qty | Avg Price | LTP | P&L | Product.
   * Holdings table:

     * Symbol | Qty | Avg Price | Current Value | Unrealized P&L.
   * Action: optional manual square-off via Zerodha order.

6. **Analytics**

   * Filters: date range, strategy, symbol.
   * KPIs:

     * Total P&L, Win rate, Avg win, Avg loss, Max DD.
   * Charts:

     * P&L over time.
     * P&L by symbol.
     * P&L by time of day.
   * Table of closed trades (entry/exit orders, R:R).

7. **Settings**

   * Tabs:

     * **Execution Settings**:

       * Default mode (AUTO/MANUAL) per strategy.
       * Default product/order type.
       * Simulation mode toggle (global).
     * **Risk Management**:

       * Max order value, max qty, daily loss limits.
       * Short sell protection.
       * Whitelists/blacklists.
     * **Broker Connection**:

       * Connect/disconnect Zerodha.
       * Show token expiry and last refresh.

8. **System Logs (Optional, nice-to-have)**

   * Filterable list of events (info/warn/error).
   * Good for debugging.

---

## 8. User Stories (Examples)

1. **Auto Execution**

   * *As a trader*, when a TradingView alert fires for a strategy set to **AUTO**, I want the order to be sent directly to Zerodha, so I don’t have to intervene manually.

   **Acceptance Criteria:**

   * Alert with valid `secret` is received.
   * Order passes risk checks.
   * Zerodha order is placed and visible in Order History with corresponding ID.
   * If it fails, I see clear error in activity feed and Order History.

2. **Manual Queue**

   * *As a cautious trader*, I want alerts from certain strategies to land in a **Waiting Queue**, so I can adjust quantity and price before executing.

   **Acceptance Criteria:**

   * Strategy in MANUAL mode → orders appear in Waiting Queue.
   * I can change quantity and switch between MARKET and LIMIT.
   * On clicking “Execute”, order passes RM and goes to Zerodha.
   * Queue item status updates accordingly.

3. **Risk Limit Enforcement**

   * *As a risk-aware trader*, I want to prevent over-sized positions, so I don’t blow up my account due to a strategy or alert bug.

   **Acceptance Criteria:**

   * If incoming order exceeds max qty or value, system clamps or rejects as per config.
   * UI shows that RM modified or rejected the order.
   * Trade logs record these decisions.

4. **Broker Connection**

   * *As a user*, I want to connect my Zerodha account once and use it for all automated orders.

   **Acceptance Criteria:**

   * I can complete a simple flow to link my Zerodha account.
   * Connection status is shown on dashboard.
   * If token expires, app surfaces a clear reconnection prompt.

5. **Analytics**

   * *As a strategy user*, I want to see how each strategy performs, so I can decide which ones to keep in AUTO mode.

   **Acceptance Criteria:**

   * I can filter analytics by strategy and date range.
   * I see summary metrics and P&L curve.
   * Trades table shows entry/exit data for each closed trade.

---

## 9. Non-Functional Requirements

* **Reliability**

  * Handle bursts of alerts (e.g., multiple symbols on same bar).
  * Ensure DB writes are atomic and consistent.
* **Performance**

  * Latency from alert receipt to order placement should be minimal (dominated by network + broker).
* **Security**

  * HTTPS for external endpoints.
  * TradingView secret key.
  * Encrypted sensitive data (tokens, credentials).
* **Maintainability**

  * Clear modular code structure:

    * `core` (domain models).
    * `services` (RM, order routing).
    * `adapters` (Zerodha API).
    * `api` (FastAPI routers).
* **Observability**

  * Log levels (INFO, WARN, ERROR) configurable.
  * Correlation IDs per alert/order for tracing.

---

## 10. ASCII Wireframes

(Monospace font helps these make sense.)

### 10.1 Main Layout

```text
+-------------------------------------------------------------+
|  Top Bar:  [Logo]  [Dashboard] [Queue] [Orders] [Analytics] |
|           [Positions] [Settings]        [User] [Status: OK] |
+-------------+-----------------------------------------------+
|             |                                               |
|  Sidebar    |   Main Content Area                           |
|             |                                               |
|  - Dashboard|                                               |
|  - Queue    |                                               |
|  - Orders   |                                               |
|  - Positions|                                               |
|  - Analytics|                                               |
|  - Settings |                                               |
+-------------+-----------------------------------------------+
```

### 10.2 Dashboard

```text
+-------------------------------------------------------------+
|  Dashboard                                                  |
+-------------------------------------------------------------+
| Today P&L   | Executed Trades | Auto Strategies | Conn Stat |
|  ₹ +12,500  |       14        |      3          | Zerodha ✓ |
+-------------------------------------------------------------+
|                  Equity Curve (Chart)                       |
|  [-----------------------------------------------]          |
+-------------------------------------------------------------+
| Recent Activity                                            v|
|  [10:05] Order EXECUTED: BANKNIFTY BUY 50 @ 45000          |
|  [10:03] Alert RECEIVED: Zero Lag Trend Strategy           |
|  [09:58] Order REJECTED (Risk: Max Qty exceeded)           |
+-------------------------------------------------------------+
```

### 10.3 Waiting Queue (Manual Orders)

```text
+-------------------------------------------------------------+
|  Waiting Queue (Manual Orders)                             |
+-------------------------------------------------------------+
| Filters: [Strategy v] [Symbol v] [Side v] [Search____]      |
+-------------------------------------------------------------+
| Strategy       | Symbol | Side | Qty  | Price   | Type |Prod|
|-------------------------------------------------------------|
| Zero Lag Trend | SBIN   | BUY  | [100]|[ 800.5 ]| MKT | MIS |
|                |        |      |      |         |(v)  |(v)  |
|   [Execute] [Cancel]     Received: 10:02:15                |
|-------------------------------------------------------------|
| Breakout Strat | RELI   | SELL | [50 ]|[ 2800 ]| LMT | CNC |
|   [Execute] [Cancel]     Received: 10:01:10                |
+-------------------------------------------------------------+
| Legend: Type = MARKET/LIMIT; Prod = MIS/CNC                |
+-------------------------------------------------------------+
```

### 10.4 Order History

```text
+-------------------------------------------------------------+
| Orders History                                              |
+-------------------------------------------------------------+
| Filters: [Date: Today v] [Strategy v] [Status v] [Symbol v] |
+-------------------------------------------------------------+
| Time     | Strategy       | Symbol | Side | Qty | Price |Sts|
|-------------------------------------------------------------|
| 10:05:12 | Zero Lag Trend | SBIN   | BUY  | 100 | 800.5 |EXE|
| 10:03:44 | Breakout Strat | RELI   | SELL |  50 | 2800  |REJ|
| 09:59:10 | Zero Lag Trend | HDFCB  | BUY  |  75 | 1500  |OPN|
+-------------------------------------------------------------+
| Click row → Drawer with:                                    |
| - Zerodha Order ID                                          |
| - Raw Alert JSON                                            |
| - Risk changes                                              |
| - Broker response logs                                      |
+-------------------------------------------------------------+
```

### 10.5 Analytics

```text
+-------------------------------------------------------------+
| Analytics                                                   |
+-------------------------------------------------------------+
| [Strategy v] [Date From____] [Date To____] [Apply]          |
+-------------------------------------------------------------+
| Summary:                                                    |
|  Total P&L:   ₹ +45,000                                     |
|  Win Rate:    62%                                           |
|  Max Drawdown: -₹ 8,500                                     |
|  Avg R:R:     1.8                                           |
+-------------------------------------------------------------+
| P&L Over Time (Chart)                                      |
| [-----------------------------------------------]           |
+-------------------------------------------------------------+
| Trades Table                                               v|
| Entry Time | Exit Time | Symbol | Side | Qty | P&L | R:R   |
|-------------------------------------------------------------|
| ...                                                       ...|
+-------------------------------------------------------------+
```

### 10.6 Settings – Risk Management

```text
+-------------------------------------------------------------+
| Settings > Risk Management                                  |
+-------------------------------------------------------------+
| Global Limits                                               |
|  Max order value: [ 100000 ]                                |
|  Max qty per order: [ 200 ]                                 |
|  Max daily loss: [ 15000 ]                                  |
|  Allow short selling? [x]                                   |
+-------------------------------------------------------------+
| Strategy-Specific                                           |
|  Strategy: [Zero Lag Trend v]                               |
|   Execution Mode: [AUTO v]                                  |
|   Max order value: [ 50000 ]                                |
|   Max qty: [ 100 ]                                          |
|   Symbol whitelist: [SBIN, HDFCB, RELI]                     |
+-------------------------------------------------------------+
| [Save Changes]                                              |
+-------------------------------------------------------------+
```

---

If you like this direction, next step could be:

* Define the **exact REST API endpoints** (request/response schemas).
* Define the **SQLite schema** in more detail (DDL).
* Then we can start implementing: FastAPI skeleton, React layout, and a basic version of the webhook → queue → Zerodha pipeline.
