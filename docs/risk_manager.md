# SigmaTrader-managed risk exits (SL / trailing SL / trailing profit)

SigmaTrader can manage broker-independent exits for equity orders by:
- monitoring LTP
- computing stop/trailing triggers
- submitting a single exit order (MARKET by default)

This is implemented as a background service (`managed-risk`) and persists
state in the database so it is restart-safe.

## RiskSpec

Orders can optionally carry a `risk_spec` payload which is stored as JSON on
the `orders.risk_spec_json` column.

Example:

```json
{
  "stop_loss": { "enabled": true, "mode": "PCT", "value": 2.0, "atr_period": 14, "atr_tf": "5m" },
  "trailing_stop": { "enabled": true, "mode": "PCT", "value": 1.0, "atr_period": 14, "atr_tf": "5m" },
  "trailing_activation": { "enabled": true, "mode": "PCT", "value": 3.0, "atr_period": 14, "atr_tf": "5m" },
  "exit_order_type": "MARKET"
}
```

### Distance modes

- `ABS`: distance = `value` (₹)
- `PCT`: distance = `entry_price * value/100`
- `ATR`: distance = `ATR(period, timeframe) * value`

ATR is computed using the market data service (`candles`), and the resulting
distance is persisted on the managed position at entry-fill time.

## Managed state (restart-safe)

When an entry order transitions to `EXECUTED` and contains a valid `risk_spec`,
SigmaTrader creates a row in `managed_risk_positions`:

- `entry_price`
- `best_favorable_price`
- `trail_price`
- `is_trailing_active`
- `last_ltp`
- `status`: `ACTIVE | EXITING | EXITED`
- `exit_order_id`, `exit_reason`: `SL | TRAIL | MANUAL`

## Execution model

The managed risk loop runs every `ST_MANAGED_RISK_POLL_INTERVAL_SEC` seconds
(default `2s`) and:

1. loads `ACTIVE` / `EXITING` managed positions
2. fetches LTP (broker quote API)
3. updates trailing state
4. transitions `ACTIVE -> EXITING` via compare-and-set to ensure idempotency
5. submits exactly one exit order (MARKET)

## Settings

- `ST_MANAGED_RISK_ENABLED` (default `true`)
- `ST_MANAGED_RISK_POLL_INTERVAL_SEC` (default `2.0`)
- `ST_MANAGED_RISK_MAX_PER_CYCLE` (default `200`)

## Notes / constraints

- SELL-side managed risk is only enabled for `product= MIS` (intraday shorts).
- Exit orders are marked with `orders.is_exit=true` so they are not blocked by
  entry-risk policies that disallow SELL.

