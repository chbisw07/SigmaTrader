# AngelOne (SmartAPI) Support — Prework

This document summarizes what needs to be aligned in SigmaTrader before implementing support for a second broker: **AngelOne via SmartAPI** (alongside the existing **Zerodha via Kite**).

Scope of this report:
- Identify frontend areas that are currently Zerodha-first and should become broker-agnostic.
- Assess frontend + backend changes required for AngelOne/SmartAPI.
- Call out design considerations and open questions to resolve before implementation.

---

## 0) Current State (quick snapshot)

### Existing multi-broker scaffolding (already present)
- Global broker list in config: `backend/app/config_files.py` (`brokers`, `default_broker`).
- Per-user broker secrets store: `backend/app/models/broker.py` + `backend/app/services/broker_secrets.py` + `/api/brokers/*` (`backend/app/api/brokers.py`).
- Per-user broker connections table: `backend/app/models/broker.py` (`BrokerConnection`).
- Settings UI already lists brokers + secrets: `frontend/src/views/SettingsPage.tsx`.

### Where the app is still Zerodha-centric (examples)
- Dedicated Zerodha connect API: `backend/app/api/zerodha.py` (login-url/connect/status + margins/ltp + order preview).
- Order execution is hard-wired to Zerodha client: `backend/app/api/orders.py` (`_get_zerodha_client`, Zerodha GTT flow).
- Positions/holdings sync is Zerodha-only: `backend/app/api/positions.py`, `backend/app/services/positions_sync.py`.
- Market data instrument resolution is Kite/Zerodha-only and caches Kite instrument_token:
  - `backend/app/services/market_data.py` uses Kite instruments fallback.
  - `backend/app/models/market_data.py:MarketInstrument` lacks `broker_name`, so tokens are implicitly Zerodha/Kite tokens.
- UI strings, labels, and actions mention Zerodha directly across many pages:
  - `frontend/src/views/QueuePage.tsx` (LTP/margins/preview + “send to Zerodha” copy).
  - `frontend/src/views/HoldingsPage.tsx`, `frontend/src/views/DashboardPage.tsx`, `frontend/src/views/PositionsPage.tsx`, `frontend/src/views/OrdersPage.tsx`, `frontend/src/views/SettingsPage.tsx`, etc.

---

## 1) Frontend alignment needed BEFORE adding AngelOne

These are the UX areas that currently assume “there is one broker (Zerodha)” and should be made broker-aware first.

### 1.1 Broker identity must become a first-class UI concept
Today, the user can *select a broker* in Settings for secrets, but most of the app behaves as though Zerodha is “the broker”.

Suggested alignment:
- Introduce a shared concept of **Active Broker** (per user) used by:
  - Holdings/positions universe selection
  - Queue execution target and broker-specific capabilities
  - Any broker-side previews (margins/charges)
  - Broker-sync actions (orders sync / holdings sync / positions sync)
- Decide where the user selects Active Broker:
  - Option A: Global selector (top bar / settings-level default).
  - Option B: Per-page selector (Dashboard, Holdings, Queue).
  - Option C: Hybrid (global default + per-page override).

### 1.2 Settings page: broker connection UX should be generalized
Current: broker secrets table is generic, but the “Connect” flow is Zerodha-only (`selectedBroker === 'zerodha'`).
- File: `frontend/src/views/SettingsPage.tsx`

Suggested alignment:
- Refactor broker connection UI into broker-specific subcomponents, e.g.:
  - `ZerodhaConnectCard`
  - `AngelOneConnectCard`
- Keep the generic “secrets table” and “broker selector” shared.

### 1.3 Holdings / Dashboard / Screener labels and semantics
Examples:
- “Include Holdings (Zerodha)” appears in multiple screens:
  - `frontend/src/views/DashboardPage.tsx`
  - `frontend/src/views/ScreenerPage.tsx`
- Holdings page describes Zerodha explicitly: `frontend/src/views/HoldingsPage.tsx`

Suggested alignment:
- Replace strings with “Holdings (BrokerName)”, driven by Active Broker.
- If multiple brokers are connected, allow:
  - View holdings per broker
  - Or optionally merged holdings across brokers (requires design decisions).

Also update other user-facing Zerodha-first copy so the app reads broker-agnostic:
- Alerts target labels: `frontend/src/views/AlertsPage.tsx` (“Holdings (Zerodha)”).
- Orders/Positions sync CTAs: `frontend/src/views/OrdersPage.tsx`, `frontend/src/views/PositionsPage.tsx` (“Refresh from Zerodha”).
- Landing/auth marketing copy: `frontend/src/views/AuthPage.tsx` (Zerodha mentions).
- Universe metadata: `frontend/src/universe/holdingsAdapter.ts` (“Holdings (Zerodha)”, “Zerodha (Kite)”).

### 1.4 Queue/Orders: broker-specific features must be surfaced as capabilities
Examples:
- Queue uses Zerodha-specific preview and GTT UI:
  - `frontend/src/views/QueuePage.tsx` (“Place as GTT at Zerodha”, Zerodha margins/LTP/preview calls)

Suggested alignment:
- Model broker capabilities in UI:
  - `supportsGtt`, `supportsOrderMarginsPreview`, etc.
- Show/hide fields and validations accordingly (e.g., GTT toggle may not exist for AngelOne or may behave differently).

Practical implication: services and error copy should also become broker-aware:
- `frontend/src/services/zerodha.ts` is Zerodha-only today; views import it directly (Queue/Orders/Settings).
- `frontend/src/services/positions.ts` embeds “sync positions from Zerodha” copy.

### 1.5 Universe/market symbol validation is currently “Kite-centric”
Group import and symbol resolution relies on Kite fallback (`allow_kite_fallback`) and `MarketInstrument` cache:
- `frontend/src/views/GroupsPage.tsx` passes `allow_kite_fallback`.
- Backend implementation is Zerodha/Kite instruments-based: `backend/app/services/market_data.py`.

Suggested alignment:
- Decide whether universe validation should be:
  - broker-specific (recommended), or
  - exchange-only (NSE/BSE) independent of broker (still needs broker token mapping for data fetch/execution).

---

## 2) FE + BE changes required for AngelOne/SmartAPI support (assessment)

This section focuses on concrete code changes likely needed.

### 2.1 Backend: introduce an AngelOne client + connection APIs
Current pattern:
- Zerodha APIs live under `/api/zerodha`: `backend/app/api/zerodha.py`
- Zerodha client wrapper: `backend/app/clients/zerodha.py`

Likely additions:
- `backend/app/clients/angelone.py` (SmartAPI wrapper; similar “Protocol + thin adapter” approach).
- `backend/app/api/angelone.py`:
  - `GET /api/angelone/status`
  - `POST /api/angelone/connect` (session creation)
  - Optional: `POST /api/angelone/disconnect`
  - AngelOne equivalents for:
    - LTP quote
    - margins/funds
    - order preview (if supported)
    - order book sync (if needed)

Critical backend modeling gap:
- `BrokerConnection` currently stores a single `access_token_encrypted`.
  - SmartAPI typically needs more than one token (JWT + refresh/feed tokens), plus expiry metadata.
  - You will likely need to extend `BrokerConnection` to store either:
    - multiple encrypted fields, or
    - a single encrypted JSON blob (recommended for extensibility).

### 2.2 Backend: broker-agnostic order execution path
Current:
- `backend/app/api/orders.py` executes against Zerodha (`_get_zerodha_client`) and stores `zerodha_order_id`.
- `backend/app/services/order_sync.py` syncs statuses from Zerodha order book via `zerodha_order_id`.

Required changes:
- Add `broker_name` to `Order` rows (or derive from strategy/account context).
- Replace `zerodha_order_id` with a broker-agnostic `broker_order_id` (DB migration + schema + UI).
  - Files: `backend/app/models/trading.py`, `backend/app/schemas/orders.py`, `frontend/src/services/orders.ts`, `frontend/src/views/OrdersPage.tsx`.
- Refactor execution logic to a broker interface:
  - `execute_order` chooses the correct broker client by `broker_name`.
  - GTT must be capability-driven (Zerodha-only today).

### 2.3 Backend: holdings/positions/snapshots must become broker-aware
Current:
- `/api/positions/sync` is Zerodha-only: `backend/app/api/positions.py`
- Sync implementation is Zerodha-only: `backend/app/services/positions_sync.py`

Required changes:
- Decide whether positions tables should:
  - store broker_name per row, or
  - be per “active broker” only (simpler but less flexible).
- Update schemas and UI to show which broker the data came from (if multi-broker view is supported).

### 2.4 Backend: market data service must be decoupled from Kite tokens
This is the biggest structural blocker for multi-broker support.

Current:
- `MarketInstrument.instrument_token` is implicitly a **Kite instrument_token**.
- `market_data.py` resolves tokens and fetches history using KiteConnect.

Options:
1) **Broker-specific instrument cache** (recommended):
   - Add `broker_name` to `MarketInstrument` (unique constraint becomes `broker_name,symbol,exchange`).
   - Maintain separate tokens for Zerodha and AngelOne.
2) **Exchange-only candle store** (broker-independent):
   - Fetch history from a non-broker market-data provider (or a single broker) and treat as universal.
   - Still need broker instrument mapping for execution/LTP.

Either way, for AngelOne support you need a plan for:
- instrument master download/refresh (SmartAPI provides instruments list).
- mapping TradingView symbols to broker tradingsymbols/tokens (see also `load_zerodha_symbol_map` in `backend/app/config_files.py`).

### 2.5 Frontend service layer
Current:
- Zerodha-specific calls live in `frontend/src/services/zerodha.ts`.
- Queue page imports Zerodha calls directly: `frontend/src/views/QueuePage.tsx`.

Required changes:
- Introduce a broker-agnostic service facade, e.g. `frontend/src/services/brokerRuntime.ts`:
  - `getStatus(broker)`
  - `connect(broker, payload)`
  - `getLtp(broker, symbol, exchange)`
  - `getMargins(broker)`
  - `previewOrder(broker, payload)` (optional/capability-driven)
- Migrate views to call the generic facade and branch by active broker/capabilities.

---

## 3) Design changes / considerations for AngelOne support

### 3.1 Broker account selection and “default broker”
You already have:
- `brokers` and `default_broker` in config (`backend/app/config_files.py`).

You need to decide:
- Can a user connect **multiple brokers simultaneously**?
- If yes, which one is “active” by default, and per which scope?
  - global app default
  - per user
  - per strategy
  - per order

### 3.2 Capability matrix (avoid lowest-common-denominator UX)
Don’t force the UI to only expose what all brokers support.
Instead:
- Define a capabilities model and adapt UI accordingly:
  - GTT (Zerodha) vs no-GTT (AngelOne) vs alternative order types
  - margin preview availability
  - supported products/varieties/order types (CNC/MIS, SL/SL-M, etc.)

### 3.3 Token lifecycle + reconnect UX
SmartAPI sessions typically expire and require refresh/re-login more often than Kite access tokens.
Design considerations:
- Show token expiry/health in Settings.
- Background refresh vs manual reconnect flows.
- Auditable events (system events) on token refresh failures.

### 3.4 Instrument universe and symbol mapping
You already have a Zerodha symbol-map config (`backend/app/config_files.py:load_zerodha_symbol_map`).
For AngelOne you’ll likely need:
- a similar mapping mechanism (or unified mapping keyed by broker_name).
- a strategy for derivatives/series (EQ, BE, etc.) differences per broker.

### 3.5 Risk engine and paper trading
Paper engine uses Zerodha LTP for fills: `backend/app/services/paper_trading.py`.
If AngelOne is added:
- Decide whether paper trading should use:
  - a broker-neutral price source, or
  - the active broker’s quote API.

---

## 4) Open questions to answer before implementation

### Product/UX
1) Should the user be able to connect both Zerodha and AngelOne at the same time?
2) Should “Holdings/Positions” screens show:
   - broker-specific datasets (tabbed), or
   - merged positions across brokers?
3) Should strategies be tied to a broker (e.g., “execute on AngelOne”), or does “LIVE” always mean “current active broker”?
4) Do we need AngelOne support for:
   - only manual queue execution, or
   - TradingView → auto execution as well?

### Backend/data model
5) How should we refactor `Order.zerodha_order_id`?
   - Rename to `broker_order_id` and add `broker_name` (recommended).
   - Migration strategy for existing rows?
6) How should we store SmartAPI token set?
   - Extend `BrokerConnection` to store JSON (encrypted) + expiry timestamps?
7) How should we handle instrument tokens for both brokers?
   - Add `broker_name` to `MarketInstrument` (recommended).
   - Or centralize price/history elsewhere?

### Broker feature parity
8) Which order types/products must be supported for AngelOne at v1?
   - MARKET/LIMIT/SL/SL-M
   - CNC/MIS
   - any AngelOne-specific variety fields
9) Is there an AngelOne equivalent of Zerodha GTT that we want to support?
10) Are margin/charges previews available in SmartAPI, and if not, what does the UI show for “funds required”?

### Ops/security
11) SmartAPI auth typically needs a second factor (TOTP/PIN/OTP).
   - How do we want the connect flow to work in the UI without compromising secrets?
12) Rate limits and background polling:
   - what’s the safest polling cadence for quotes/orderbook?
   - do we need backoff, caching, and broker-specific throttling?

---

## Suggested implementation approach (phased)

**Phase 0 (alignment/refactor):**
- Make broker selection and capability model explicit.
- Refactor `Order` model away from Zerodha-specific fields.
- Refactor market instruments to be broker-aware (or decide an alternative).

**Phase 1 (AngelOne connect + minimal runtime):**
- Add `angelone` to `backend/config/config.json` brokers list.
- Implement `backend/app/api/angelone.py` connect/status.
- Add AngelOne connect card in `frontend/src/views/SettingsPage.tsx`.

**Phase 2 (Execution + sync):**
- Implement AngelOne order placement + status sync.
- Update Queue/Orders UI to select broker and show broker order id.

**Phase 3 (Holdings/positions/market data):**
- Implement AngelOne holdings/positions sync and display.
- Implement AngelOne instrument master integration if required.
