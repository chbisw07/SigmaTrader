# Product-Specific Risk Engine v2 (CNC/MIS) — Manual Verification

This doc is for manually verifying the **product-specific risk engine v2** implementation from `docs/product_specific_risk_and_drawdown_plan.md`.

## Prereqs

- Run DB migrations:
  - `alembic upgrade head`
- Enable v2 enforcement:
  - Set `ST_RISK_ENGINE_V2_ENABLED=1` and restart the backend.
- Ensure a TradingView webhook secret is configured:
  - Settings → TradingView webhook → Secret

## One-time configuration

1) Settings → Risk settings → **Product-specific risk profiles (CNC/MIS)**
   - Create at least one enabled profile (CNC and/or MIS).
   - Mark one profile per product as **Default**.
   - For MIS profiles, configure:
     - `leverage_mode` (AUTO/STATIC/OFF)
     - `max_effective_leverage`
     - `max_margin_used_pct`

2) Settings → Risk settings → **Drawdown thresholds**
   - Fill thresholds for `(product, category)` pairs.

3) Groups → (Portfolio or Watchlist) → **Category** column
   - Assign each traded symbol a category: `LC/MC/SC/ETF`.

## Tests

### A) Baseline: webhook → queue

1) Create a TradingView alert that posts to `POST /webhook/tradingview`.
2) Send a payload **without** quantity (SigmaTrader sizes from profile):
   - `trade_details.quantity = null`
3) Confirm:
   - Alert is accepted (201)
   - A `WAITING` order appears in Queue/Orders.

### B) v2 sizing + execution

1) Ensure v2 is enabled (`ST_RISK_ENGINE_V2_ENABLED=1`).
2) Execute the `WAITING` order.
3) Confirm:
   - `order.qty` is auto-sized.
   - If MIS and leverage/margin caps apply, qty may be clamped.
   - Order is either `SENT` or `REJECTED_RISK` with a clear reason.

### C) Drawdown gating (NORMAL/CAUTION/DEFENSE/HALT)

1) Lower the drawdown thresholds for the order’s `(product, category)` so the current DD% crosses:
   - CAUTION, then DEFENSE, then HARD STOP.
2) Execute a new entry order each time.
3) Confirm behavior:
   - CAUTION: throttled sizing
   - DEFENSE/HALT: blocks new entries (exits still allowed)

### D) MIS safety guards

1) Slippage guard:
   - Set `slippage_guard_bps` to a low value (e.g. `5`).
   - Execute an entry order where LTP deviates above the threshold.
   - Confirm: blocked with a slippage-guard reason.

2) Gap guard:
   - Set `gap_guard_pct` to a low value.
   - Execute an entry order when the gap is above the threshold.
   - Confirm: blocked with a gap-guard reason.

### E) Idempotency / dedupe

1) Post the same TradingView payload twice with a stable `order_id`.
2) Confirm the second request returns:
   - `status = "deduped"`
   - `order_id` is the same as the first.

### F) Legacy compatibility

1) Post an existing legacy “flat” TradingView payload (no `meta/signal/hints`).
2) Confirm:
   - Order is accepted and processed as before.

