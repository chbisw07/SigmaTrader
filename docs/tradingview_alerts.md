# TradingView Alerts → SigmaTrader (Webhook Guide)

This guide shows how to send **TradingView alerts** to **SigmaTrader** using the webhook endpoint and how to interpret/debug what happens next (queue orders, execution mode, common errors).

## 1) What you get

When TradingView fires an alert, SigmaTrader:

1. Receives your webhook payload at `POST /webhook/tradingview` (or the compat alias `POST /webhook`).
2. Stores it as an **Alert** row in the database.
3. Creates a corresponding **Order**:
   - **MANUAL** strategies → order lands in **Queue Management** with status `WAITING`
   - **AUTO** strategies → SigmaTrader tries to execute immediately (LIVE broker or PAPER engine)

## 2) Prerequisites / setup

### A) Backend config

SigmaTrader reads env vars with prefix `ST_`.

Set the TradingView secret in `backend/.env`:

```
ST_TRADINGVIEW_WEBHOOK_SECRET=my-secret
```

If `ST_TRADINGVIEW_WEBHOOK_SECRET` is set, incoming payload must include the same `"secret"` value, otherwise the webhook returns `401 Invalid webhook secret.`

### B) Start backend + frontend

- Backend: FastAPI on `http://localhost:8000`
- Frontend UI: Vite on `http://localhost:5173`

### C) Expose the webhook publicly (ngrok)

TradingView needs a public URL. The simplest approach is `ngrok`:

1. Start:
   - `ngrok http 8000`
2. Copy your forwarding URL (example):
   - `https://<your-subdomain>.ngrok-free.app`
3. Use this as webhook URL in TradingView:
   - `https://<your-subdomain>.ngrok-free.app/webhook/tradingview`

Debugging tip: ngrok provides an inspector UI:

- `http://127.0.0.1:4040`

This is the fastest way to see the **actual request body** TradingView sent and the **exact 4xx validation error** returned by SigmaTrader.

## 3) The webhook endpoint(s)

Preferred:

- `POST http://localhost:8000/webhook/tradingview`

Backwards-compatible alias (accepts the same payload):

- `POST http://localhost:8000/webhook`

Quick check:

- `GET http://localhost:8000/webhook`

## 4) TradingView message template (recommended)

SigmaTrader expects a JSON object. TradingView will replace placeholders like `{{exchange}}` / `{{ticker}}` / `{{interval}}` / `{{close}}`.

### Recommended (ST Strategy v6): Order fills alert + `{{strategy.order.alert_message}}`

If you are using SigmaTrader’s TradingView Strategy v6 (or any Pine strategy that sets `alert_message=` on `strategy.entry/close/exit`), configure **one** TradingView alert:

- Alert type: **Strategy → Order fills**
- Webhook URL: `.../webhook/tradingview`
- Message: `{{strategy.order.alert_message}}`

In this mode, the **strategy itself** generates the JSON (typically `{ meta, signal, hints }`) and TradingView forwards it verbatim. This is more reliable than maintaining multiple `alertcondition()` templates.

Important: for numeric fields like `price` and `quantity`, **do not put the placeholder in quotes**.

### A) Limit order (recommended default)

This makes SigmaTrader create a `LIMIT` order because `price` is provided.

```json
{
  "secret": "my-secret",
  "platform": "TRADINGVIEW",
  "st_user_id": "admin",
  "strategy_name": "TV-01",
  "symbol": "{{exchange}}:{{ticker}}",
  "exchange": "{{exchange}}",
  "interval": "{{interval}}",
  "trade_details": {
    "order_action": "BUY",
    "quantity": 1,
    "price": {{close}},
    "product": "CNC",
    "comment": "TV alert: {{exchange}}:{{ticker}} @ {{close}}"
  }
}
```

### B) Market order (omit `price`)

This makes SigmaTrader create a `MARKET` order because `price` is missing.

```json
{
  "secret": "my-secret",
  "platform": "TRADINGVIEW",
  "st_user_id": "admin",
  "strategy_name": "TV-01",
  "symbol": "{{exchange}}:{{ticker}}",
  "exchange": "{{exchange}}",
  "interval": "{{interval}}",
  "trade_details": {
    "order_action": "BUY",
    "quantity": 1,
    "product": "CNC",
    "comment": "TV alert MARKET: {{exchange}}:{{ticker}}"
  }
}
```

### C) Flat format (also accepted)

SigmaTrader also accepts a “flat” payload (without nesting under `trade_details`):

```json
{
  "secret": "my-secret",
  "platform": "TRADINGVIEW",
  "st_user_id": "admin",
  "strategy_name": "TV-01",
  "symbol": "{{exchange}}:{{ticker}}",
  "exchange": "{{exchange}}",
  "interval": "{{interval}}",
  "order_action": "BUY",
  "quantity": 1,
  "price": {{close}},
  "product": "CNC",
  "comment": "TV alert: {{exchange}}:{{ticker}} @ {{close}}"
}
```

## 5) Field reference (what SigmaTrader currently uses)

Top-level fields:

- `secret` (string, required): must match `ST_TRADINGVIEW_WEBHOOK_SECRET` if set.
- `platform` (string, default `TRADINGVIEW`):
  - Accepted: `TRADINGVIEW`, `ZERODHA` (case-insensitive check in backend)
  - Any other value will be **ignored** (SigmaTrader returns `{ "status": "ignored" }`).
- `st_user_id` (string, recommended/required):
  - Must match an existing SigmaTrader `User.username`.
  - If missing / unknown, the alert is **ignored** (not an error).
- `strategy_name` (string, required):
  - If a matching Strategy exists in SigmaTrader, it controls routing:
    - `execution_mode=AUTO` and `enabled=true` → SigmaTrader attempts immediate execution
    - otherwise → MANUAL (lands in `WAITING`)
  - If the strategy is not found, SigmaTrader still stores the alert and creates a MANUAL order.
- `symbol` (string, required):
  - Recommended format: `{{exchange}}:{{ticker}}` (example `NSE:INFY`)
  - SigmaTrader derives broker exchange/symbol from this.
- `exchange` (string, optional):
  - If `symbol` already has `NSE:`/`BSE:` prefix, this is redundant.
- `interval` (string, optional): stored for context (examples: `1`, `5`, `15`, `D`).
- `bar_time` (datetime, optional): can be included if you generate it.

`trade_details` fields (or flat equivalents):

- `order_action` (string, required): must be exactly `BUY` or `SELL` (case-insensitive; normalized server-side).
- `quantity` (number, optional but strongly recommended): if omitted, SigmaTrader treats it as `0`.
- `price` (number, optional):
  - If present → order becomes `LIMIT`
  - If omitted → order becomes `MARKET`
- `product` (string, optional): `CNC` (delivery) or `MIS` (intraday). Defaults to `MIS`.
- `trade_type` (string, optional): alternate way to set product (e.g. `cash_and_carry` → `CNC`).
- `comment` / `alert_message` (string, optional): stored as the alert “reason” for traceability.

## 5.1 Important SELL behavior (qty resolution + exit-only safety)

BUY alerts generally use the TradingView `quantity` as-is.

SELL alerts are more complex because a SELL can mean either:

- an exit (sell existing holdings / close an open position), or
- a fresh short sell (sell without an existing position).

SigmaTrader treats **TradingView SELL as exit-first** to avoid accidental shorting and broker rejections:

- If SigmaTrader can fetch broker state, it will:
  - Prefer **holdings qty** (delivery) when available and use it as the SELL qty.
  - Otherwise, fall back to **open positions qty** (intraday/delivery) and use it as the SELL qty.
-  If neither holdings nor a long position exists, SigmaTrader will still create a **WAITING** order (MANUAL) so you can review/edit (qty/product) before execution.
- If SigmaTrader cannot fetch broker state (not connected / temporary broker error), it falls back to the TradingView payload qty (legacy behavior).

Practical implications:

- Your TradingView SELL `quantity` may be overridden when SigmaTrader can confirm your actual holdings/position.
- To do deliberate short-selling (SELL without position), use:
  - manual order entry, or
  - SigmaTrader deployments/strategies designed for shorting (future/advanced flow).

## 6) How to interpret what you see in SigmaTrader

### A) Where to see incoming alerts / orders

- **Queue Management**: newly created MANUAL orders appear in the `WAITING` queue.
- **System Events**: helpful when something is ignored (e.g. missing `st_user_id`).

### B) Why prices look “rounded”

SigmaTrader enforces a tick size of **0.05** for order prices (limit orders / GTT / rebalance / webhook orders), using nearest-tick rounding.

Examples:

- `320.29` → `320.30`
- `320.26` → `320.25`

This prevents broker rejections when the exchange tick rule is 0.05.

## 7) Common problems and fixes

### A) 404 Not Found

Cause:
- Posting to the wrong path (e.g. `/api/webhook` or something else).

Fix:
- Use `.../webhook/tradingview` (preferred) or `.../webhook` (compat).

### B) 401 Invalid webhook secret

Cause:
- `"secret"` in the payload does not match `ST_TRADINGVIEW_WEBHOOK_SECRET`.

Fix:
- Ensure the payload contains:
  - `"secret": "<same value as backend/.env>"`

### C) 422 Unprocessable Entity (schema validation failure)

This is the most common TradingView issue.

Typical causes:

- You are **sending invalid JSON** (missing commas/braces).
- `order_action` is not `BUY`/`SELL` (example: `"buy"` is ok only if SigmaTrader receives it as a string; but `"{{something}}"` is not).
- `price` / `quantity` are not numbers (common when placeholders are quoted or not replaced).

Fix checklist:

1. Confirm TradingView message is valid JSON.
2. Ensure numeric placeholders are not quoted:
   - ✅ `"price": {{close}}`
   - ❌ `"price": "{{close}}"`
3. Open `http://127.0.0.1:4040` (ngrok inspector), click the failing request, and copy the `detail` error message. It will point to the exact bad field.

### D) Alert “accepted” but nothing appears in queue

Possible causes:

- The alert was **ignored** because:
  - `st_user_id` missing, or
  - `st_user_id` does not match an existing SigmaTrader username.

Fix:
- Use a valid SigmaTrader username in `"st_user_id"`.

## 8) Examples (copy/paste)

### Example 1: CNC Buy (Limit at close)

```json
{
  "secret": "my-secret",
  "platform": "TRADINGVIEW",
  "st_user_id": "admin",
  "strategy_name": "TV-CNC-BUY",
  "symbol": "{{exchange}}:{{ticker}}",
  "interval": "{{interval}}",
  "trade_details": {
    "order_action": "BUY",
    "quantity": 10,
    "price": {{close}},
    "product": "CNC"
  }
}
```

### Example 2: MIS Sell (Market)

```json
{
  "secret": "my-secret",
  "platform": "TRADINGVIEW",
  "st_user_id": "admin",
  "strategy_name": "TV-MIS-SELL",
  "symbol": "{{exchange}}:{{ticker}}",
  "interval": "{{interval}}",
  "trade_details": {
    "order_action": "SELL",
    "quantity": 1,
    "product": "MIS"
  }
}
```

### Example 3: Use `exchange` + `ticker` (when you prefer to build symbol)

SigmaTrader can derive `symbol` if you omit it but include `exchange` and `ticker`:

```json
{
  "secret": "my-secret",
  "platform": "TRADINGVIEW",
  "st_user_id": "admin",
  "strategy_name": "TV-03",
  "exchange": "{{exchange}}",
  "ticker": "{{ticker}}",
  "interval": "{{interval}}",
  "trade_details": {
    "order_action": "BUY",
    "quantity": 1,
    "price": {{close}},
    "product": "CNC"
  }
}
```

## 9) Symbol mapping (when TradingView symbol != broker symbol)

By default SigmaTrader assumes TradingView symbol codes match the broker. If you ever face symbol mismatches, you can add a mapping file:

- `backend/config/zerodha_symbol_map.json`

Example:

```json
{
  "NSE": {
    "SCHNEIDER": "SCHNEIDER-EQ"
  }
}
```

## 10) Screenshots (optional)

If you want this guide to embed your exact screenshots, save them into:

- `docs/images/tradingview_alerts/`

Suggested filenames:

- `tv_alert_message.png`
- `ngrok_console_422.png`
- `ngrok_inspect_422.png`
- `postman_success.png`
- `queue_orders_created.png`

Then reference them from this doc (standard Markdown image links).
