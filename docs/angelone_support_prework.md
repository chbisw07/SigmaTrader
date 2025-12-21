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

## 0.1) Key decisions (agreed so far)

These decisions shape the implementation plan and what becomes “broker-scoped” vs “broker-agnostic”.

1) **Multiple brokers active simultaneously**
- [Decided] For a single SigmaTrader user, support `1× Zerodha(Kite) + 1× AngelOne(SmartAPI) + ...` connected and usable at the same time.
- Settings should show broker cards for each supported broker; user can connect/disconnect independently.
- Note: the current DB shape already aligns with “1 connection per (user, broker)” via `BrokerConnection` unique constraint (`backend/app/models/broker.py`).

2) **Single, broker-agnostic groups/universe**
- Groups (watchlists/baskets) stay **broker-agnostic** and represent the NSE/BSE “stock universe” (not tied to a broker).
- Core group identity remains `(exchange, symbol)` for now; broker-specific tokens/tradingsymbols are resolved at runtime.

3) **Holdings remain broker-scoped**
- Holdings page should offer separate views: “Holdings (Zerodha)” and “Holdings (AngelOne)”.
- Holdings are broker-scoped datasets; we should not silently merge them unless explicitly requested.

4) **Dashboard holdings overlay**
- [Decided] Dashboard “Include Holdings” includes holdings from all connected brokers by default (rest of dashboard behavior unchanged).
- [Decided] Add broker checkboxes (Zerodha, AngelOne, …) so the user can include/exclude per broker.

5) **Alerts become broker-aware**
- Alerts should be targeted as `<broker>:<symbol>` (and likely `<broker>:<exchange>:<symbol>` to avoid ambiguity).
- Rationale: when an alert triggers an action (BUY/SELL), the execution broker is explicit.

6) **Positions view is broker-specific**
- [Decided] Positions screen should be broker-specific (tabs/dropdown), not silently merged.

7) **Execution is always broker-bound**
- [Decided] Any strategy/alert that can execute (BUY/SELL) is always bound to a destination broker for execution.
- This implies “execution broker” is required data in: strategies, alert action templates, and manual queue execution.

8) **AngelOne parity**
- [Decided] AngelOne support level should match Zerodha (manual queue + TradingView auto execution + sync flows), subject to broker capability differences.

9) **ISIN is available for AngelOne**
- [Decided] SmartAPI instrument master includes ISIN; we can use it to strengthen cross-broker symbol mapping.

10) **Alert evaluation uses canonical data**
- [Decided] Evaluate alerts on a canonical market-data pipeline; at trigger/execution time do broker-scoped validation (mapping + optional broker quote).

11) **Alert targeting uses first-class columns**
- [Decided] Add first-class alert target columns (`broker_name`, `symbol`, `exchange`) rather than encoding `<broker>:<exchange>:<symbol>` into a string.

12) **Default execution broker storage**
- [Decided] Store execution broker:
  - per strategy (default for automation),
  - per alert action template (required for alert actions),
  - per user as a fallback default for manual actions (Queue).

13) **“All brokers” views are limited**
- [Decided] Avoid “All brokers” views broadly to prevent UX bloat.
- Allowed/expected:
  - Settings → Broker settings (always “all brokers” by nature)
  - Dashboard holdings overlay (checkboxes across brokers)
- Elsewhere (Orders/Positions/Holdings): default to explicit broker selection (tabs/dropdown).

14) **GTT is Zerodha-only**
- [Decided] Only Zerodha supports API-level GTT today; treat it as a broker capability.
- UI/BE must disable/hide GTT for brokers that do not support it (AngelOne).

15) **SmartAPI connect UX**
- [Decided] AngelOne connect requires the user to enter OTP/PIN when a session is created (no background refresh that stores additional sensitive credentials).

16) **Canonical market-data provider (v1)**
- [Decided] Use Zerodha as the canonical candles/quotes source for consistency.
- [Decided] If Zerodha is not connected/healthy, canonical evaluation pauses and the UI surfaces a prominent “Market data unavailable” state (no automatic fallback in v1 to preserve consistency).

17) **Margin/charges preview fallback**
- [Decided] If a broker cannot provide margin/charges preview, UI shows “N/A” and still allows execution (with a warning).

18) **Synthetic GTT for non-native brokers**
- [Decided] For brokers without native API-level GTT, support “server-side conditional orders” (SigmaTrader-managed) as a synthetic GTT mechanism.
- This is the default path for bracket-like workflows on non-GTT brokers.

19) **Configuration-first (Settings-driven)**
- [Decided] Prefer configurable settings (via Settings UI) whenever a behavior is likely to vary across brokers/users or needs tuning over time (polling, throttles, fallbacks, feature toggles).
- Guardrails:
  - Don’t add settings “just in case” (avoid UX bloat and configuration drift).
  - Provide safe defaults; validate ranges; and keep sensitive values out of settings (secrets stay in broker secrets).
  - Prefer capability-driven behavior over user-toggles where possible.

---

## 0.2) Decisions log (Q/A table)

This table captures the important questions, your decision, the recommended action, and what it would cost if we chose the opposite.

| Topic / Question | Decision (you) | Recommended action (we will do) | If we go against it (impact/risk) |
|---|---|---|---|
| Multi-broker usage | 1× per broker per SigmaTrader user (Zerodha + AngelOne simultaneously) | Keep `BrokerConnection` unique per `(user_id, broker_name)`; broker-aware UI (tabs/filters) | Supporting multiple accounts per broker later would require schema changes (e.g., `(user_id, broker_name, broker_user_id)` uniqueness + UI changes). |
| Broker parity + capability-driven UX | Same support level, but disable features per broker if unsupported | Add capability matrix and branch UI/BE behavior by broker | Without capability-driven design, we end up with “lowest common denominator” UX or hard failures when a broker lacks a feature. |
| Dashboard holdings overlay | Include holdings from all connected brokers by default; allow broker checkboxes | Persist selected broker-checks; aggregate overlay symbols across selected brokers | If we only include one broker, dashboard becomes misleading for users trading on multiple brokers; if we always include all without checkboxes, user loses control/noise increases. |
| Holdings view | Separate broker-specific holdings views | Provide “Holdings (Zerodha)” + “Holdings (AngelOne)” options; keep datasets broker-scoped | If we silently merge holdings, totals and analytics become ambiguous (avg cost, realized P&L, corporate actions) and debugging becomes hard. |
| Positions view | Broker-specific tabs/dropdown | Positions screen becomes broker-filtered by default; allow “All brokers” only if explicitly designed later | Merged positions can hide broker-specific constraints (product/order types) and complicate risk and P&L semantics. |
| Strategy/alert execution broker | Always broker-bound | Add `broker_name` to strategy and to alert action templates; require broker selection for manual queue execution | If broker is implicit, we get non-deterministic execution and “which broker did it trade?” issues; multi-broker is not safe. |
| AngelOne execution scope | Same as Zerodha (manual + TradingView auto execution) | Implement AngelOne for the same runtime surfaces (connect, sync, queue, alerts actions) subject to capabilities | If AngelOne is manual-only, the automation story becomes inconsistent; UI/BE will accumulate special-casing. |
| Alert evaluation data source | Canonical evaluation + broker-scoped validation at execution time | Evaluate DSL on canonical market-data pipeline; at trigger time resolve broker mapping + optional broker quote check | If we do broker-scoped evaluation: duplicated evaluation workload per broker, higher rate-limit risk, more token-expiry churn, harder debugging, and scaling pains. |
| Orders schema | Replace `zerodha_order_id` → `broker_order_id` + `broker_name` | Migrate DB + services + UI; show broker in Orders grid | Keeping Zerodha-specific ids blocks multi-broker, breaks sync logic, and forces per-broker ad-hoc columns forever. |
| Broker sessions (tokens) | Use same mechanism but SmartAPI requires multiple tokens | Store encrypted JSON session blob + expiry metadata in `BrokerConnection`; keep Zerodha compatible via `{access_token}` | If we keep single token field, we’ll bolt on extra tables/columns per broker later and make token refresh flows brittle. |
| Broker secret naming | Keep internal keys generic, rename env-var aliases/labels (`KITE_API_KEY`, `SMARTAPI_API_KEY`) | Continue using `BrokerSecret(broker_name, key)` with keys like `api_key`, `api_secret`; only improve naming in env/docs/UI labels | If we bake broker names into secret keys, we duplicate logic and increase misconfiguration risk (wrong key looked up). |
| Canonical instrument identity | Use ISIN-backed canonical model | Implement canonical instrument/listing + broker-instrument mapping with ISIN as stable identifier | If we avoid canonical identity, symbol mismatches across brokers cause “works on Zerodha but not on AngelOne” failures; fixes become per-symbol hacks. |
| Alerts targeting schema | First-class columns (broker_name, symbol, exchange), not string encoding | Add columns + migrate; keep `target_ref` for `GROUP` and legacy | If we encode into a string: parsing brittleness, weaker constraints, harder indexing, and painful migration when you inevitably need structured fields. |
| Default execution broker storage | Per strategy + per alert action template + per-user fallback | Store on strategy (automation) + on alert action template (alerts); keep per-user fallback for manual queue | If stored only per-user, automation becomes ambiguous; if stored only per-order, UX becomes repetitive and error-prone. |
| “All brokers” view (Orders/Positions) | Limited use only | Avoid broad “all brokers” views; keep explicit broker selection on most pages | Broad “all brokers” grids become noisy, hard to filter, and create unclear semantics for actions like refresh/sync/execute. |
| GTT support | Zerodha-only | Capability-gate GTT features (Queue + alert actions); hide/disable for AngelOne | If we try to “fake” GTT parity, users will see broken actions; if we show GTT everywhere, it will confuse AngelOne users. |
| Instrument tokens + history (multi-broker) | Canonical `security/listing/broker_instrument` | Prefer canonical `security/listing/broker_instrument` model; keep broker-specific tokens in mapping tables | If we keep only per-broker instrument tables without canonical linkage, cross-broker consistency breaks and symbols drift into per-broker hacks. |
| Migration strategy | Dual-read/dual-write + backfill | Dual-read/dual-write + backfill for alerts/orders/instruments; cut over after validation | Single “big bang” cutover risks downtime and data inconsistencies; too-long dual-mode increases maintenance cost. |
| Holdings API shape | Broker-parameterized endpoints | Broker-parameterize common endpoints where the shape is the same (e.g., `/positions/holdings?broker_name=`) | Separate per-broker endpoints increases duplication; overly-generic endpoints can hide broker-specific differences if responses diverge. |
| HOLDINGS alerts in multi-broker | Broker-specific by default | Make holdings alerts broker-specific (explicit `broker_name`), add “all brokers” as explicit option later | Implicit “all holdings” can create confusing triggers and ambiguous execution scope. |
| Capability matrix ownership | Backend authoritative | Backend is authoritative; FE consumes via `/api/brokers/capabilities` | FE hardcoding becomes stale and causes mismatched UX vs backend behavior. |
| Canonical market-data provider | Zerodha-only (v1) | Use Zerodha candles/quotes for canonical evaluation; no automatic fallback in v1; add caching and health surfacing | If we introduce fallback sources, evaluation behavior can shift across providers; if Zerodha is down, evaluation pauses until it recovers (must be surfaced clearly). |
| SmartAPI connect UX (2FA/PIN/TOTP) | Manual OTP/PIN entry | Require user OTP/PIN during connect/session creation; do not store sensitive factors for background refresh | Background refresh would require storing additional secrets (higher security risk) and increases blast radius on compromise. |
| Rate limits / polling | Conservative defaults + configurable | Centralize caching + per-broker throttling/backoff; expose key cadences as settings for tuning | Without throttling/caching, multi-broker doubles API load and causes intermittent failures; without configurability, tuning requires code deploys. |
| Margin/charges preview availability | Allow execution without preview | Show “N/A” and allow execution with warning when preview isn’t available | Blocking execution reduces usefulness; allowing without warning can surprise users with insufficient funds or higher charges. |
| Synthetic GTT for non-native brokers | SigmaTrader-managed conditional orders | Implement server-side conditional orders with persistent state + monitoring + execution validation | Without this, non-Zerodha brokers cannot support bracket-like workflows; with it, we must accept operational responsibility (uptime/latency) and communicate the trade-offs. |
| Configuration-first approach | Prefer settings for tunables | Add a small, typed Settings registry (system/user/strategy scopes) and wire to Settings UI | Over-configuring increases UX bloat and makes issues harder to reproduce; under-configuring makes operations brittle and requires frequent deploys. |

---

## 1) Frontend alignment needed BEFORE adding AngelOne

These are the UX areas that currently assume “there is one broker (Zerodha)” and should be made broker-aware first.

### 1.1 Broker identity must become a first-class UI concept
Today, the user can *select a broker* in Settings for secrets, but most of the app behaves as though Zerodha is “the broker”.

With “multiple brokers active simultaneously”, the UI should treat broker choice as:
- **Broker-scoped datasets**: holdings, positions, orders, broker connection health.
- **Broker choice for actions**: where an order is placed / which broker API is called.

Suggested alignment:
- Replace “Active Broker” (singular) with a small broker context model:
  - **Connected brokers**: what accounts are connected + status per broker.
  - **Execution broker**: selected when placing orders (Queue, Alerts actions, manual trades).
  - **View broker**: selected when viewing broker-scoped datasets (Holdings, Positions, Orders).
- UX placements:
  - Holdings/Positions: broker tabs or a broker dropdown.
  - Queue: broker selector near “Execute” (defaults to last used broker).
  - Orders: show broker column; filter by broker.
  - Dashboard: keep existing toggle but treat holdings overlay as “from any connected broker(s)” per decision 0.1.

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

Given decision 0.1 (“groups are broker-agnostic”), the practical requirement becomes:
- Maintain a **canonical instrument identity** in the app (for groups, charts, indicators).
- Maintain **broker-specific mappings** from canonical instrument → broker token/tradingsymbol.
- Do not “force convert AngelOne symbols to Zerodha symbols” in the UI layer; instead resolve mappings in a dedicated mapping service.

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
  - Recommendation: store an **encrypted JSON session blob** + expiry metadata.
    - Keep Zerodha compatible by storing `{ "access_token": "..." }` in the same shape.
    - Store SmartAPI as `{ "jwt": "...", "refresh": "...", "feed": "...", "expires_at": "..." }` (exact fields TBD).
  - This still follows the “same mechanism for AngelOne as Zerodha”: per-user `BrokerConnection` row storing encrypted session material.

### 2.2 Backend: broker-agnostic order execution path
Current:
- `backend/app/api/orders.py` executes against Zerodha (`_get_zerodha_client`) and stores `zerodha_order_id`.
- `backend/app/services/order_sync.py` syncs statuses from Zerodha order book via `zerodha_order_id`.

Required changes:
- Add `broker_name` to `Order` rows (or derive from strategy/account context).
- [Decided] Replace `zerodha_order_id` with a broker-agnostic `broker_order_id` and add `broker_name` (DB migration + schema + UI).
  - Files: `backend/app/models/trading.py`, `backend/app/schemas/orders.py`, `frontend/src/services/orders.ts`, `frontend/src/views/OrdersPage.tsx`.
- Refactor execution logic to a broker interface:
  - `execute_order` chooses the correct broker client by `broker_name`.
  - GTT must be capability-driven (Zerodha-only today).

Given decision 0.1 (“multiple brokers active simultaneously”):
- Orders list should display the broker (`broker_name`) and allow filtering by it.
- Queue execution must choose a broker explicitly (no implicit “Zerodha” default).

### 2.3 Backend: holdings/positions/snapshots must become broker-aware
Current:
- `/api/positions/sync` is Zerodha-only: `backend/app/api/positions.py`
- Sync implementation is Zerodha-only: `backend/app/services/positions_sync.py`

Required changes:
- Decide whether positions tables should:
  - store broker_name per row, or
  - be per “active broker” only (simpler but less flexible).
- Update schemas and UI to show which broker the data came from (if multi-broker view is supported).

Given decision 0.1 (“holdings remain broker-scoped”):
- Add an AngelOne holdings endpoint (or broker-parameterize the existing one):
  - `GET /api/positions/holdings?broker_name=zerodha|angelone`
- Keep holdings on-demand (no DB cache) initially, but include the broker name in response for clarity.

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

Given decision 0.1 (“single broker-agnostic universe”), the mapping layer becomes a first-class requirement.
Two viable approaches (for context):
1) **Introduce a canonical instrument table** and attach ISIN (preferred if available):
   - Canonical instrument key: `(exchange, symbol)` plus `isin` (for stable cross-broker matching).
   - Broker mapping table: `(broker_name, exchange, broker_symbol, broker_token, canonical_instrument_id)`.
2) **Stay with `(exchange, symbol)` as canonical key** and use best-effort broker matching:
   - Works only if AngelOne and Zerodha symbol conventions match reliably for your universe.
   - Still needs a broker mapping cache; ISIN can be added later.

Given ISIN availability (decision 0.1 #9), the canonical-table approach is preferred for long-term correctness:
- A practical normalized model is:
  - `security` (keyed by `isin`, name, metadata)
  - `listing` (exchange + symbol → `security_id`)
  - `broker_instrument` (broker_name + broker token + broker tradingsymbol → `listing_id`)
This keeps groups broker-agnostic (listing), and execution resolves listing → broker_instrument per broker.

Decision:
- [Decided] Use the ISIN-backed canonical model (`security/listing/broker_instrument`).

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

Decisions + implications:
- [Decided] A user can connect **multiple brokers simultaneously** (1× per broker per SigmaTrader user).
- [Decided] Store **execution broker**:
  - per strategy (default for automation),
  - per alert action template (required for alert actions),
  - per user as a fallback default for manual actions (Queue).

### 3.2 Capability matrix (avoid lowest-common-denominator UX)
Don’t force the UI to only expose what all brokers support.
Instead:
- Define a capabilities model and adapt UI accordingly:
  - GTT (Zerodha) vs no-GTT (AngelOne)
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

### 3.6 Configuration strategy (Settings UI)
We already have a Settings page with broker/risk/strategy settings (`frontend/src/views/SettingsPage.tsx`) and an example of a tunable operational setting (`paper_poll_interval_sec` per strategy).

Principles:
- Make **tunable operational parameters** configurable so we can maintain and tune without redeploying.
- Keep **secrets** in broker secrets (never in general settings).
- Keep user-facing settings minimal and meaningful; keep “advanced/ops” settings gated to Admin if needed.

Recommended scopes:
- **System/global** (admin): polling cadences defaults, throttling/backoff knobs, synthetic GTT evaluation loop enabled, canonical market-data “pause on missing” behavior.
- **User**: preferred execution broker fallback for manual actions; dashboard holdings broker checkbox selection.
- **Strategy**: execution broker; strategy-level polling/automation knobs (already present pattern).

Implementation suggestion:
- Introduce a small “settings registry” in backend (typed schema + validation + defaults) and expose via `/api/settings/*`.
- Frontend: add a new Settings tab (or extend existing Strategy settings) to surface only high-value knobs.

### 3.7 Alert evaluation data source (broker-scoped vs broker-neutral)
Two approaches exist:

**A) Broker-scoped evaluation**
- Pros:
  - Uses the same broker’s price feed/instrument mapping as execution.
  - Avoids “evaluated on data we can’t trade” if the broker lacks the instrument.
- Cons:
  - Higher API usage and rate-limit pressure (duplicate evaluation per broker).
  - More moving pieces (token expiry, per-broker candle quirks), harder to debug.
  - Requires two full market-data stacks (or careful caching) to scale.

**B) Broker-neutral evaluation (single canonical market-data source)**
- Pros:
  - Single consistent OHLCV/quote source for all alerts; simpler to scale and cache.
  - Evaluations are broker-independent; fewer rate limit failures.
- Cons:
  - Potential mismatch vs broker execution prices/timestamps.
  - Evaluation may trigger on an instrument that fails broker mapping at execution time unless guarded.

Recommendation (to balance correctness + scalability):
- Use broker-neutral evaluation for most indicator/candle logic, backed by a canonical instrument model (listing/ISIN).
- At trigger/execution time, do a broker-scoped “last mile” validation:
  - resolve listing → broker instrument
  - fetch broker LTP (or quote) if needed
  - only then place order on the broker
This provides deterministic evaluation while keeping execution correct and broker-specific.

Decision:
- [Decided] Use canonical evaluation + broker-scoped validation at execution time (not per-broker evaluation).

If you prefer broker-scoped evaluation for simplicity early on:
- Make it an explicit per-alert setting (data source = `canonical` | `broker`) so we can migrate without breaking behavior.

### 3.8 Alert targeting schema (string encoding vs first-class columns)
Current model (`backend/app/models/alerts_v3.py`):
- `target_kind` in `SYMBOL|HOLDINGS|GROUP`
- `target_ref` is a string (non-null)
- `exchange` optional

Options:
**A) Encode `<broker>:<exchange>:<symbol>` into `target_ref`**
- Pros: minimal DB schema changes; quickest to ship.
- Cons: parsing brittleness, weaker constraints, harder indexing, awkward migrations later.

**B) Add first-class columns**
- Add `broker_name` (nullable) + reuse `exchange` + add `symbol` (nullable), keeping `target_ref` for `GROUP` (group_id) and legacy.
- Pros: strong validation, easy indexing/filtering, cleaner FE forms, less parsing.
- Cons: requires DB migration and dual-read/dual-write while backfilling.

Recommendation:
- Prefer first-class columns (B) to keep the data model clean and scalable, especially since execution is always broker-bound (decision 0.1 #7).
- Keep `target_ref` for `GROUP` targets and for backward compatibility during migration.

Decision:
- [Decided] Implement first-class columns for broker/symbol/exchange targeting.

### 3.9 Synthetic GTT (server-side conditional orders) for non-native brokers
Problem:
- Zerodha supports API-level GTT; most other popular brokers do not (AngelOne, Upstox, HDFC Securities, Fyers…).
- We also want bracket-like workflows (entry + target + stop) even when brokers don’t provide native OCO/BO/GTT primitives.

Idea (assimilated):
- Implement “GTT-like” behavior in SigmaTrader itself:
  - Store the conditional orders in our DB (not at broker).
  - Continuously evaluate trigger conditions using canonical market data (Zerodha) + broker-scoped validation at execution time.
  - When a trigger fires, place a normal order on the destination broker (AngelOne/Fyers/etc.).

What this enables:
- **Synthetic GTT** for brokers without GTT: stop-loss/target triggers monitored by SigmaTrader.
- **Synthetic bracket orders**: model OCO logic on our side (when one exit fills, cancel/disable the other).

Design notes / guardrails (required for safety):
- Clearly label this in UI as “Server-side conditional order (SigmaTrader)” vs “Broker GTT (Zerodha)”.
- Persist a state machine per conditional order:
  - `PENDING` → `TRIGGERED` → `ORDER_PLACED` → `FILLED|REJECTED|CANCELLED|EXPIRED`
- Execution-time validation:
  - Resolve canonical instrument → broker instrument.
  - Optionally fetch broker quote (LTP) before placing, to reduce mismatch risk.
- Robustness:
  - Must survive restarts (DB-persisted state).
  - Add polling/backoff + idempotency keys to avoid duplicate placements.
  - Add monitoring/health: if evaluation loop is down, surface prominent warnings.
- Latency/slippage disclaimer:
  - Unlike broker-side GTT, server-side triggers can miss fast moves or open-gap behavior during outages; users must accept this trade-off.

Recommended hybrid approach for risk reduction (especially for stop-loss):
- If the broker supports placing a stop-loss order type (SL/SL-M), prefer placing the stop-loss on the broker immediately after entry fill (broker-side protection),
  while keeping target/OCO management server-side when needed.
  This reduces worst-case risk if SigmaTrader goes down.

---

## 4) Remaining open questions (before implementation)

These are the few remaining decisions that materially affect architecture, UX, and operational stability.

### AngelOne functional parity details
- Order/product/type parity scope for v1 AngelOne:
  - Recommended default for v1: match the same order types/products already used in Zerodha flows (at least `MARKET/LIMIT/SL/SL-M` and `CNC/MIS`), then expand as needed.
- GTT:
  - [Decided] Zerodha-only; ship without GTT for AngelOne unless/until AngelOne provides an equivalent.
- Margin/charges preview:
  - confirm whether SmartAPI supports an equivalent preview endpoint; UI fallback is already decided (“N/A” + allow execution with warning).

### SmartAPI connect UX + security
- SmartAPI auth flow details (2FA/PIN/TOTP):
  - [Decided] Require user OTP/PIN entry for session creation (no background refresh storing additional sensitive factors).
  - [Decided] Start with a Zerodha-like UX: the user completes broker login and then provides the minimum required “session completion” inputs.
    - Likely required for AngelOne: client code + PIN, and (if needed) TOTP/OTP.
    - Prefer PIN-only if SmartAPI supports it reliably; otherwise PIN + TOTP/OTP.
  - Remaining: confirm the exact SmartAPI login inputs required by the chosen auth flow and whether session refresh requires repeating the full flow or a shorter refresh step (we will start with “repeat connect” for safety).

### Ops: rate limits and polling
- Rate limits and background polling:
  - [Decided] Start with conservative defaults and tune later; always implement backoff + caching + broker-specific throttling.
  - Suggested defaults (v1):
    - Order book sync: every 5–10s when there are active/pending orders, otherwise every 30–60s.
    - Positions refresh: manual by default; optional background refresh every 60–180s.
    - Quotes/LTP: cache per `(broker, instrument)` for 1–2s for UI use; for synthetic GTT evaluation prefer canonical candles/quotes and avoid per-broker quote polling except at trigger time.

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
