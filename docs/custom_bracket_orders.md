# Custom Bracket Orders – Design Notes

This document captures the current design for **custom bracket orders** initiated from the Holdings Buy/Sell dialog in SigmaTrader. The goal is to let you place a normal order *plus* a follow‑up GTT order in one step, while keeping everything inside the existing manual queue and risk framework.

Bracket orders here are *not* Zerodha’s native “bracket order” product; they are a thin layer of logic on top of SigmaTrader’s own `Order` + `GTT` support.

---

## 1. Concept and intent

### 1.1 What a “bracket” means in this app

For each manual trade from Holdings you may optionally attach a **follow‑up GTT leg** with the same quantity and the opposite side:

- **BUY bracket**
  - Primary order: BUY (MARKET / LIMIT / SL / SL‑M) as configured in the existing dialog.
  - Secondary leg: SELL **LIMIT + GTT** order with the same quantity, at a profit‑target price above the entry.

- **SELL bracket**
  - Primary order: SELL (closing or trimming the position).
  - Secondary leg: BUY **LIMIT + GTT** order with the same quantity, at a re‑entry price below the exit (so you can buy back cheaper after taking profit).

Both legs are stored as `WAITING` manual orders in the queue. You decide when to execute them; the follow‑up leg is only sent to Zerodha when you explicitly execute it from the queue.

### 1.2 Min Target Profit (MTP) and dynamic default

The bracket logic is controlled by a **Min Target Profit** (`MTP`) expressed in percent:

- `mtp` is the user‑visible percentage.
- Internally we use `m = mtp / 100`.

The core formulas:

- **BUY + profit‑target SELL GTT**
  - Effective entry price: `P_entry` (limit price for LIMIT/SL, or an LTP/last_price proxy for MARKET).
  - Target SELL price:
    - `P_target = P_entry * (1 + m)`.

- **SELL + re‑entry BUY GTT**
  - Effective exit price: `P_exit`.
  - Re‑entry BUY price that gives `mtp` profit if price revisits `P_exit`:
    - `P_exit / P_reentry - 1 = m` ⇒ `P_reentry = P_exit / (1 + m)`.

#### Dynamic default for MTP

Instead of a fixed default (e.g. 5%), MTP should **pre‑fill from the position’s current appreciation** at the time of the order:

- For SELL from holdings:
  - Let `P_cost` be your average price from holdings.
  - Let `P_limit` be the LIMIT price you set in the dialog (or an LTP proxy if you keep MARKET).
  - Current P&L % at that limit price is:
    - `x = (P_limit / P_cost - 1) * 100`.
  - Default `MTP` is set to `x` (clamped to a sensible range), so that the re‑entry GTT is initially sized to “round‑trip” the move you are about to capture.
  - You can always override MTP manually; the UI should show both:
    - current position P&L %, and
    - the chosen MTP % that will drive the bracket leg.

- For BUY from holdings:
  - There is no “appreciation” yet for the new shares, so we use:
    - either the last used MTP for that user, or
    - a reasonable default (e.g. 5%) persisted per user.
  - The user can edit MTP at any time; we show the derived profit target in price terms.

The **MTP value and derived price** should be clearly visible and editable in the dialog; no hidden maths.

### 1.3 Manual invocation first, alerts later

In Phase‑1, bracket behaviour is **only triggered manually**:

- You open the Holdings dialog, select side, sizing, order type, and optionally tick “Add follow‑up GTT”.
- The app computes and previews the bracket leg.
- On “Create order”, both legs are created in the manual queue.

Later phases can connect this to the alert/strategy engine:

- An indicator rule (e.g. “RSI > 80 & in uptrend”) could propose a bracketed SELL or BUY.
- When you accept the suggested trade, the same bracket logic is applied behind the scenes.

---

## 2. Backend behaviour

### 2.1 What we already have

The backend already supports:

- `Order.order_type` in `{'MARKET', 'LIMIT', 'SL', 'SL-M'}`.
- `Order.gtt: bool`.
- GTT execution path in `/api/orders/{id}/execute` that:
  - Accepts **LIMIT + gtt=true** orders.
  - Uses `trigger_price` if set, otherwise uses `price` as both trigger and limit for Zerodha GTT.

No schema changes are strictly required for Phase‑1.

### 2.2 Representing bracket legs

Each leg is just a standard manual order:

- Primary:
  - `side`: BUY or SELL.
  - `qty`: derived from the sizing mode.
  - `price`: as configured in the dialog (or `null` for MARKET).
  - `order_type`: as chosen (MARKET, LIMIT, SL, SL‑M).
  - `gtt`: `false`.

- Secondary (bracket) leg:
  - `side`: opposite of primary (`BUY ↔ SELL`).
  - `qty`: same as primary (clamped to holdings for SELL).
  - `order_type`: **LIMIT** (for now).
  - `price`: `P_target` (BUY bracket) or `P_reentry` (SELL bracket).
  - `trigger_price`: can either be `price` or left `None` so the execution path uses the limit price as trigger.
  - `gtt`: `true`.

Optionally we can later add:

- A `bracket_group_id` or `parent_order_id` column to relate legs, but this is not required for Phase‑1, where manual review of the queue is acceptable.

### 2.3 Risk and execution

- Both legs go through the existing risk engine:
  - If global or per‑strategy limits block the leg, it will be rejected at creation or execution time.
- Execution semantics:
  - You typically execute the primary leg first (to realise the initial move).
  - You execute the secondary GTT leg when you’re satisfied with the position and want to park the follow‑up order at Zerodha.
  - GTT validation remains as today: only LIMIT orders with positive prices are accepted.

---

## 3. Holdings dialog UX changes

### 3.1 New “Bracket / follow‑up GTT” section

In the existing Buy/Sell from holdings dialog:

- Add a **Bracket / follow‑up GTT** section under order type:

  - Checkbox (side‑specific label):
    - BUY: `Add profit‑target SELL GTT`.
    - SELL: `Add re-entry BUY GTT`.
  - `Min target profit (MTP) %` input:
    - Pre‑filled with:
      - For SELL: current appreciation `x%` computed from LIMIT price vs average price.
      - For BUY: last‑used MTP or a default (e.g. 5%).
    - Editable; persisted per user for convenience.
  - Read‑only preview:
    - BUY: `Will create SELL GTT @ ₹P_target (+MTP% from entry).`
    - SELL: `Will create BUY GTT @ ₹P_reentry (≈MTP% profit if price revisits this level).`

### 3.2 Interaction with sizing modes and order types

- The bracket logic always uses the **final derived qty** and **effective price**:
  - Works with Qty / Amount / % of position / % of portfolio / Risk modes.
  - For MARKET orders, uses a sizing price proxy (last_price or best estimate) just for computing P_target/P_reentry and the MTP preview.
- Constraints:
  - Secondary leg is always `LIMIT + GTT`.
  - If the primary is SELL, qty is clamped to holdings, and the secondary BUY uses that clamped qty.
  - We round prices to a sensible tick (e.g. 0.05) and show rounded values in the preview and in the queue.

### 3.3 Stop‑loss helpers (advisory in Phase‑1)

To integrate stop‑loss thinking without over‑complicating the bracket:

- Add optional SL helper controls inside the dialog:
  - Mode: `Manual` / `ATR multiple`.
  - Manual: user sets a stop price or stop %, and we show implied ₹ and % risk for the primary leg.
  - ATR: use existing `ATR(14)%` and an ATR multiple `k` to suggest a stop:  
    `stop = entry - k * ATR_abs` (for BUY) or the symmetric formula for SELL.
- In Phase‑1 this remains **advisory**:
  - It can feed into the risk‑based sizing mode.
  - It is not yet turned into an automatic second SL GTT leg.
  - Later, if desired, we can extend the design to create dual GTT legs (target + stop) or use Zerodha’s OCO features.

---

## 4. Backtesting idea (BSE, NETWEB, and generalisation)

To test whether this bracket logic adds value, we want a reusable backtest harness that runs on top of the existing OHLCV / market‑data infrastructure:

- Implement a **console program in the backend** that:
  - Uses the same market data fetching layer (e.g. via Kite OHLCV) as the live app.
  - Accepts parameters:
    - Symbols (e.g. `BSE`, `NETWEB`), exchange, timeframe.
    - Lookback window (e.g. trailing 1 month).
    - Entry criteria (for now, simple rules like: “Enter long whenever price makes a new N‑day high” or “Use real executed trades from holdings history”).
    - MTP logic (e.g. MTP = appreciation at SELL, or fixed X%).
  - Simulates:
    - Primary entries and exits according to the chosen rule.
    - Secondary bracket GTT legs according to the formulas above.
    - Execution of GTT legs whenever price hits their levels.
  - Reports:
    - Net P&L and P&L per symbol.
    - Win‑rate, average win/loss, and max drawdown.

The initial scope will focus on BSE and NETWEB for the last month, but the tool will be parameterised so you can run the same logic on any symbol and window without changing code.

This backtest lives as a separate sprint task and will reuse as much of the existing market‑data and indicator plumbing as possible instead of introducing a separate analytics stack.

