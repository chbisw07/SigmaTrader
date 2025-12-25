# Rebalance Dialog Help (SigmaTrader)

This page explains every field and column in the **Rebalance** dialog so you can confidently preview and place rebalance orders.

The rebalance feature is designed to be:
- **Explainable**: every trade is tied to a drift from target.
- **Budgeted**: you can cap how much gets traded.
- **Guardrailed**: drift bands, max trades, and minimum trade value reduce churn and tiny orders.

---

## 1) What “rebalance” means in SigmaTrader

SigmaTrader supports two rebalance scopes:

### A) Portfolio rebalance (Group kind = `PORTFOLIO`)
You define **target weights** per symbol in your portfolio group. Rebalance tries to bring your **live holdings weights** closer to those targets.

### B) Holdings rebalance (broker holdings universe) and `HOLDINGS_VIEW` groups
There are **no saved targets**. Rebalance assumes **equal-weight** across the symbols in the selected scope and proposes trades to reduce concentration (subject to your budget and bands).

In both cases:
- SigmaTrader estimates the current value of each position as `qty × price`.
- Computes live weights, compares to target weights, and proposes BUY/SELL orders.

---

## 2) Preview table columns (boxed in the screenshot)

Each row represents **one proposed trade**.

### `Broker`
Which broker account the trade is for (e.g. `zerodha`, `angelone`).

### `Symbol`
The tradingsymbol that will be bought or sold.

### `Side`
- `BUY`: the symbol is **underweight** vs target.
- `SELL`: the symbol is **overweight** vs target.

### `Qty`
The proposed **share quantity** (integer).

Notes:
- Quantity is derived from `trade_value / price`, then **rounded down**.
- For sells, quantity is clamped to your available holding quantity.

### `Est. price`
The **estimated price** used to size the order and compute `Est. notional`.

Source (best-effort):
- First choice: broker holdings **last price** (LTP) if available.
- Fallback: latest daily close from SigmaTrader candles (if available).

Important: this is for **estimation**; real execution price may differ.

### `Est. notional`
Estimated rupee value of the trade:

`Est. notional = Qty × Est. price`

This helps you quickly see which trades are “large” vs “small”.

### `Target`
The desired weight (percentage) for that symbol in the selected rebalance scope:
- **Portfolio rebalance**: comes from the portfolio group’s target weights.
- **Holdings/HOLDINGS_VIEW rebalance**: equal-weight target across symbols.

This is shown as a **percent of total portfolio value**.

### `Live`
The symbol’s **current weight** (percentage) right now:

`Live = current_value / total_portfolio_value`

where `current_value = holding_qty × price`.

### `Drift`
How far the live weight is from target:

`Drift = Live − Target`

Interpretation:
- Positive drift (e.g. `+8.0%`) means **overweight** → typically SELL.
- Negative drift (e.g. `−2.1%`) means **underweight** → typically BUY.

The drift shown is in **percentage points** (because `Live` and `Target` are percentages).

---

## 3) The summary line above the table

Example:
`ZERODHA — trades: 6, budget used: 84795 (9.7%), turnover: 11.8%`

### `trades`
How many trade rows are currently proposed (after all filters/constraints).

### `budget used`
How much of your configured budget is actually used.

SigmaTrader tracks buy and sell totals separately and uses:
- `budget used = max(total_buy_value, total_sell_value)`

This is a conservative way to show the bigger of the two sides.

### `budget used (%)`
Budget used as a percent of current portfolio value.

### `turnover`
An activity metric:

`turnover % = (total_buy_value + total_sell_value) / portfolio_value × 100`

Turnover will be higher than “budget used %” when both buys and sells are present.

---

## 4) Inputs in the dialog (what they do)

### `Broker`
Which broker’s holdings to use for live weights, and where orders will be created/executed.

Recommended:
- If you opened the dialog from “Holdings (Zerodha)”, keep broker as Zerodha.
- If you opened it from “Holdings (AngelOne)”, keep broker as AngelOne.

### `Budget (%)`
Caps how much of your portfolio value the rebalance is allowed to trade.

Example: if portfolio value is ₹10,00,000 and budget is 10%, budget is ₹1,00,000.

### `Budget amount (INR)` (overrides %)
If set, this becomes the absolute cap (₹). Useful when you want a fixed rupee limit.

### `Abs band (%)` (absolute drift band)
Minimum drift (in percentage points) required before a symbol is eligible for trading.

Example: if `Abs band = 2%`, a symbol with drift of `+1.2%` will be ignored.

### `Rel band (%)` (relative drift band)
A band that scales with the target weight:

`relative_threshold = rel_band × target_weight`

The effective threshold is:
`max(abs_band, relative_threshold)`

This reduces churn for small-weight positions.

### `Max trades`
Limits the number of proposed trades. When more candidates exist, SigmaTrader keeps the largest trades (by estimated notional) first.

### `Min trade value (INR)`
Drops tiny trades by requiring:
`Est. notional >= Min trade value`

### `Mode`
- `MANUAL`: creates orders in the queue (WAITING) so you can review and execute later.
- `AUTO`: attempts to execute immediately via broker integration.

### `Target`
- `LIVE`: sends real orders to your broker.
- `PAPER`: paper-trading mode (if enabled in your environment).

### `Order type`
- `MARKET`: executes at market price (price not fixed).
- `LIMIT`: uses the estimated price as the limit price (may not fill if the market moves away).

### `Product`
Broker product type, typically:
- `CNC` for delivery (common for investing/portfolio rebalances)
- `MIS` for intraday (use with care)

### `Idempotency key (optional)` (group rebalances)
Prevents accidental duplicate executions if you click twice or retry a request.

Recommendation:
- Use a short unique key per rebalance action (e.g. `pf_green_2025-12-25_1`).

---

## 5) Worked examples

### Example 1 — Portfolio rebalance with target weights
Portfolio value = ₹1,00,000

Targets:
- A: 50%
- B: 50%

Live:
- A value = ₹80,000 → Live = 80% → Drift = +30%
- B value = ₹20,000 → Live = 20% → Drift = −30%

Without budget limits, ideal would be to sell A and buy B by ~₹30,000 each.

If budget is 10% (₹10,000), SigmaTrader scales the trade sizes down proportionally, so you might see something like:
- SELL A ~₹10,000
- BUY B ~₹10,000

### Example 2 — Holdings rebalance (equal-weight)
Holdings scope has 5 symbols → equal-weight target = 20% each.

If one symbol is at 35% (drift +15%) and another at 8% (drift −12%), SigmaTrader proposes SELL for the overweight one and BUY for the underweight one, subject to:
- drift bands,
- your budget,
- and min trade value / max trades.

---

## 6) Practical safety checklist before pressing “Create queued orders” / “Execute now”

1) **Confirm scope**: are you rebalancing the correct broker and correct group/universe?
2) **Start small**: use a low budget (e.g. 2–5%) until you trust the behaviour.
3) **Use bands**: a non-zero band (e.g. 1–2%) reduces churn.
4) **Use MANUAL first**: review the queued orders before going AUTO.
5) **Watch LIMIT orders**: limit orders may not fill; MARKET is simpler for rebalancing.
6) **Check sells**: ensure you’re not selling positions you don’t want to reduce (tax/conviction).

---

## 7) Known v1 limitations (important)

- **Cash is not modeled explicitly**: portfolio value is derived from positions only; the system does not allocate a “cash weight”.
- **Price is best-effort**: LTP is preferred; otherwise last close may be used; execution can differ.
- **Integer qty rounding** can leave small residual drift.
- **No replacement/universe expansion**: rebalance trades only among the symbols in scope; it won’t add new symbols.
- **History is only stored for group rebalances** (`PORTFOLIO` / `HOLDINGS_VIEW` group scopes). Holdings-universe rebalances currently create orders without run-history storage.

