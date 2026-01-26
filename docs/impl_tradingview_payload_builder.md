# TradingView Alert Payload Builder v1 – Manual Verification

Date: 2026-01-26

## Prereqs

- Backend running on `http://localhost:8000`
- Frontend running on `http://localhost:5173`
- TradingView webhook secret configured in SigmaTrader (Settings → TradingView webhook)

## UI smoke test

1. Open `Settings → TradingView webhook → Alert Payload Builder`.
2. Confirm the screen shows a two-pane layout:
   - Left: META / SIGNAL / HINTS field builder
   - Right: Live JSON Preview
3. Confirm preview masks the secret (`"secret": "********"`).
4. Change `signal.strategy_id` and confirm preview updates immediately.
5. Click `+ Add Field`, add:
   - key: `tv_quantity`
   - type: `number`
   - value: `{{strategy.order.contracts}}`
6. Confirm preview renders numeric tokens unquoted:
   - `"price": {{close}}`
   - `"tv_quantity": {{strategy.order.contracts}}`
7. Enter an invalid hint key like `bad key` and confirm Copy is disabled until fixed.
8. Click `Copy JSON` and paste into a local text editor:
   - Confirm copied JSON contains the real secret (unmasked).

## Template persistence

1. Enter `Template name` (e.g. `TrendSwing_CNC`).
2. Click `Save Template`.
3. Click `Load Template` and confirm the template appears in the list.
4. Load it and confirm fields are restored.
5. (Optional) Delete the template from the Load dialog.

## Webhook ingestion (builder schema v1)

1. Copy JSON from the builder.
2. POST it to SigmaTrader:
   - Endpoint: `POST /webhook/tradingview`
   - Header `Content-Type: application/json`
3. Confirm response is `201` with `{ "status": "accepted", ... }`.
4. Confirm a new Alert + Order are created (Queue Management / DB).

## Backward compatibility (legacy payload)

1. Send an existing “legacy flat” TradingView payload (without `meta/signal/hints`) to:
   - `POST /webhook/tradingview`
2. Confirm it is still accepted and behaves as before.

