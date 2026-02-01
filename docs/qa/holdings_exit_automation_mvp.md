# QA: Holdings Exit Automation (MVP)

This checklist validates the end-to-end flow for **Holdings Exit Automation (MVP)**:

- Zerodha holdings are monitored
- when a configured target is met, SigmaTrader creates a **CNC SELL** order in the **Waiting Queue** (manual-only)
- the subscription is reconciled to **COMPLETED** after the order executes

## Preconditions

- Backend running
- Frontend running
- Zerodha connected and holdings available for at least one symbol
- You understand the MVP constraints:
  - `broker_name=zerodha` only
  - `product=CNC` only
  - `dispatch_mode=MANUAL` only (creates WAITING order; never auto-sends to broker)
  - `order_type=MARKET` only
  - price source is LTP
  - trigger kinds supported (MVP):
    - `TARGET_ABS_PRICE`
    - `TARGET_PCT_FROM_AVG_BUY`

## Environment Flags (Backend)

- Enable feature:
  - `ST_HOLDINGS_EXIT_ENABLED=1`
- Optional allowlist (recommended for rollout):
  - `ST_HOLDINGS_EXIT_ALLOWLIST_SYMBOLS="NSE:INFY,BSE:TCS"` (also accepts bare symbols like `INFY`)
- Engine tuning:
  - `ST_HOLDINGS_EXIT_POLL_INTERVAL_SEC=5`
  - `ST_HOLDINGS_EXIT_MAX_PER_CYCLE=200`

## Smoke: API gating

1) With `ST_HOLDINGS_EXIT_ENABLED=0`:
- Open `Queue -> Managed exits -> Holdings exits`
- Expected: API call fails with a clear error and UI shows an error message.

2) With `ST_HOLDINGS_EXIT_ENABLED=1` and allowlist set, try to create a subscription for a non-allowed symbol:
- Expected: creation blocked (403) with a rollout/allowlist message.

## Flow A: Create Subscription (via Holdings Goal UI)

1) Open `Holdings` page.
2) Click `Edit` for a symbol that exists in holdings (qty > 0).
3) Set a target:
   - `Target type = Absolute Price` and `Target value = <some value>`
   - OR `Target type = % from Avg Buy` and `Target value = <some %>`
4) Enable:
   - `Subscribe to holdings exit automation (MVP)`
   - choose sizing:
     - `% of position` (e.g. 50) OR `Qty` (e.g. 1)
5) Click `Save Goal`.

Expected:
- Goal saves successfully.
- Subscription is created (best-effort) and you can see it in:
  - `Queue -> Managed exits -> Holdings exits`

Notes:
- If subscription creation fails, the goal should still be saved and the dialog should show a clear subscription error.
- `Target type = % from LTP` is blocked for MVP.

## Flow B: Create Subscription (via Managed Exits UI)

1) Open `Queue -> Managed exits -> Holdings exits`.
2) Click `New subscription`.
3) Enter:
   - symbol (supports `INFY` or `NSE:INFY`)
   - trigger kind/value
   - sell sizing (% or qty)
4) Click `Create`.

Expected:
- Subscription appears in the table in `ACTIVE` status.
- Events show `SUB_CREATED`.

## Flow C: Trigger => Waiting Order Creation

Goal: verify trigger detection creates a **WAITING** SELL order and attaches it to the subscription.

1) Ensure the selected holding has qty > 0 in broker holdings.
2) Choose a target that will realistically be met (for QA you can:
   - set a target below current LTP so it triggers quickly
   - or temporarily use a paper/sandbox environment if available)
3) Wait for the engine to evaluate (poll interval).
4) Open subscription `Events`.

Expected:
- Events include:
  - `EVAL` entries (with price snapshot)
  - `TRIGGER_MET`
  - `ORDER_CREATED`
- Subscription transitions to:
  - `ORDER_CREATED`
  - `pending_order_id` populated
- A new order is visible in:
  - `Queue -> Waiting Queue`
  - `side=SELL`, `product=CNC`, `mode=MANUAL`, `status=WAITING`

## Flow D: User Review => Execute Order => Subscription Completes

1) In Waiting Queue, open the created order.
2) Optionally edit qty/price parameters (depending on UI capabilities).
3) Execute it manually.

Expected:
- Order progresses to broker lifecycle (SENT/EXECUTED/etc).
- On execution completion:
  - subscription transitions to `COMPLETED`
  - events include `SUB_COMPLETED`

## Reconciliation Checks (Edge Cases)

### 1) Order fails or is rejected

Make an exit order fail (e.g. invalid market state / risk policy rejection, etc.).

Expected:
- subscription transitions to `ERROR`
- event `ORDER_FAILED` is recorded
- `pending_order_id` is cleared (the user can resume/recreate)

### 2) Broker unavailable during evaluation

Disconnect Zerodha (or simulate missing token) and wait for an eval cycle.

Expected:
- subscription stays `ACTIVE`
- `last_error` is updated with broker unavailable message
- event `EVAL_SKIPPED_BROKER_UNAVAILABLE`

### 3) Missing quote (no LTP)

Simulate missing quote for a symbol (rare; easier in tests).

Expected:
- `EVAL_SKIPPED_MISSING_QUOTE` event
- no order is created

### 4) Holdings qty becomes 0

If the broker holding qty becomes 0 (already sold elsewhere):

Expected:
- subscription transitions to `COMPLETED` with reason `no_holdings`
- no order is created

## UX/Observability Expectations

- Every state transition should be explainable by events.
- The user should always have a manual way to:
  - pause / resume
  - delete the subscription
  - find the linked order in queue

## Regression Checklist

- `Queue -> Managed exits` still shows the existing “Position exits” panel.
- Quick trade flow still works.
- No new backend warnings/errors in `pytest`.
- Frontend `npm test` + `npm run build` pass.

