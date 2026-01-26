# Product-Specific Alert Ordering & Risk Enforcement Plan (SigmaTrader)

This document defines a **detailed, implementation-ready plan** to extend SigmaTrader with **product-aware (CNC / MIS) risk profiles**, **alert-to-order transformation**, and **multi-level drawdown controls** (strategy-level + portfolio-level), including **UX wireframes**.

The goal is to ensure:
- TradingView alerts are treated as *signals*, not orders
- Orders are derived based on **selected product (CNC / MIS)**
- **Product-specific risk profiles** enforce sizing, limits, and drawdowns
- Drawdown controls adapt to **volatility buckets (LC / SM / ETF)**
- System remains safe, extensible, and non-fragile

---

## 1. Design Principles (Non-Negotiable)

1. **Signal ≠ Order**  
   TradingView provides *intent + price*, SigmaTrader decides *if / how / how much*.

2. **Risk is product-aware**  
   MIS and CNC have fundamentally different leverage and failure modes.

3. **Drawdown throttles risk, not just trading**  
   Drawdowns should *adapt behavior* before forcing hard stops.

4. **Single enforcement point**  
   All risk checks must converge at one execution gateway (`execute_order_internal`).

5. **Fail closed**  
   If risk state is unknown → block execution.

---

## 2. Core Concepts & Objects

### 2.1 Alert (Input)

TradingView alert payload (simplified):
```json
{
  "source": "TRADINGVIEW",
  "strategy_id": "TrendSwing_v1",
  "symbol": "NSE:SBIN",
  "side": "BUY",
  "trigger_price": 612.5,
  "timestamp": "2026-02-01T10:15:00Z"
}
```

Alert contains **no authority** over:
- quantity
- product
- stop-loss
- execution mode

---

### 2.2 Strategy (Keep Clean)

**Goal:** keep Strategy objects focused on signal logic, not execution policy.

Revised model:
- Strategy does **not** embed risk limits, drawdown thresholds, or product enforcement logic.
- Strategy may optionally carry a *minimal identity* only (e.g., name, timeframe, tags).
- **Product selection** can be supplied in the alert payload (optional), but is always validated and may be overridden by SigmaTrader policy.

```text
Strategy:
  id: TrendSwing_v1
  name: Trend Swing v1
  timeframes: [30m, 1h, 4h]
  tags: [trend, atr]
```

**Optional (allowed) in alert message:**
- `product_hint`: CNC | MIS

> SigmaTrader remains the authority: it may reject a product hint if disallowed by configuration.

---

### 2.3 Product

Execution instrument type:

- `CNC` → delivery / swing / positional
- `MIS` → intraday / leveraged

Product is **not chosen by TradingView**.
It is derived from **RiskProfile selection**.

---

### 2.4 RiskProfile (Key Object)

RiskProfile encapsulates **all enforcement rules** that are *external to the Strategy*.

**Revisions per feedback:**
- Strategy stays clean.
- RiskProfile is selected by app config (and optionally influenced by alert `product_hint`).
- Drawdown thresholds are managed in Settings by (product, category), and RiskProfile references that configuration.

```text
RiskProfile:
  id: CNC_Swing_Default
  product: CNC

  # Position sizing
  capital_per_trade: 30000
  max_positions: 10
  max_exposure_pct: 30

  # Per-trade risk
  risk_per_trade_pct: 0.075
  hard_risk_pct: 0.10

  # Daily controls
  daily_loss_pct: 0.75
  hard_daily_loss_pct: 1.0
  max_consecutive_losses: 3

  # Drawdown (references Settings thresholds by product+category)
  drawdown_mode: SETTINGS_BY_CATEGORY

  # Time controls (CNC often null)
  force_exit_time: null
```

---

## 3. Drawdown Framework (Bucketed + Holding-Level Categories)

This section incorporates the agreed approach:
- **Category assignment happens from Holdings / Universe UI** (per symbol)
- **Drawdown thresholds are managed centrally in Settings** (per category + per product)

### 3.1 Where category is defined

**Holdings / Symbols page** maintains:
- `risk_category` per symbol: `LC | MC | SC | ETF` (you can keep MC/SC only if preferred; ETF can be optional)

This keeps drawdown tuning *portable* and avoids hard-coding it inside Strategy.

### 3.2 Where drawdown limits are defined

**Settings → Risk → Drawdown** defines max drawdown thresholds (percent) by:
- **Product**: CNC vs MIS
- **Category**: LC / MC / SC (/ ETF)

Example configuration (illustrative defaults):

| Product | Category | Caution | Defense | Hard Stop |
|---|---|---:|---:|---:|
| CNC | LC | 6% | 9% | 12% |
| CNC | MC | 9% | 14% | 18% |
| CNC | SC | 12% | 18% | 25% |
| MIS | LC | 2% | 3.5% | 5% |
| MIS | MC | 2.5% | 4% | 6% |
| MIS | SC | 3% | 5% | 7% |

> MIS thresholds are intentionally tighter because leverage compresses tolerable drawdown.

### 3.3 Drawdown scope

Drawdown is tracked at two levels:

1. **Category-level drawdown** (optional v1): equity curve for that category bucket
2. **Portfolio-level drawdown** (recommended v1): global hard stop to ensure survivability

**Practical MVP:** implement **portfolio-level drawdown first**, then add category-level if needed.

### 3.4 Drawdown state machine

```text
NORMAL   → Full risk
CAUTION  → Throttled risk
DEFENSE  → Restricted trading
HALT     → Trading paused (manual review)
```

### 3.5 Behavior by drawdown state

Behavior is applied by **RiskProfile / Product**, and can be tuned in Settings.

- **NORMAL**: full sizing, full eligibility
- **CAUTION**: throttle sizing (e.g., ×0.7), reduce max positions
- **DEFENSE**: block new entries OR allow only highest-quality signals (ETF/LC)
- **HALT**: block new entries; manage existing positions only

### 3.6 Using category in decisions

When an alert arrives for `symbol`, SigmaTrader reads:
- `symbol.risk_category` from Holdings/Universe
- applies the drawdown thresholds for (product, category)

This allows LC/MC/SC to behave differently without polluting Strategy.

## 4. Alert → Order Transformation Pipeline

```text
TradingView Alert
   ↓
Validate Source + Secret
   ↓
Resolve Strategy
   ↓
Resolve RiskProfile
   ↓
Check Product Compatibility
   ↓
Compute Drawdown State
   ↓
Apply Drawdown Throttles
   ↓
Risk Checks (ALL):
   - exposure
   - per-trade risk
   - daily loss
   - loss streak
   - drawdown state
   ↓
Compute Quantity
   ↓
Derive Order (product, qty, SL, TP)
   ↓
Execute or Block
```

If **any step fails** → order is blocked with reason logged.

---

## 5. Execution Enforcement Point

### 5.1 Single Enforcement Function

All alert execution converges to:

```text
execute_order_internal(alert)
```

Responsibilities:
1. Resolve product (CNC / MIS)
2. Load product RiskProfile
3. Resolve symbol drawdown category
4. Compute symbol + portfolio drawdown state
5. Apply drawdown throttles
6. Compute leverage-aware quantity (MIS)
7. Enforce ALL limits

If any check fails → **block order with explicit reason**.

---

## 6. UX / Wireframe Plan

### 6.1 Holdings / Symbols: Category Assignment (LC / MC / SC)

Add a column + editor to assign risk category per symbol.

```text
┌─────────────────────────────────────────────────────────────┐
│ Holdings / Symbols                                          │
├───────────┬─────────┬───────────────┬────────────┬──────────┤
│ Symbol    │ Qty     │ Avg Price     │ Category   │ Actions  │
├───────────┼─────────┼───────────────┼────────────┼──────────┤
│ SBIN      │ 120     │ 612.5         │ LC  [▼]    │ …        │
│ ANANTRAJ  │  80     │  510.0        │ SC  [▼]    │ …        │
│ SILVERETF │  50     │   85.2        │ ETF [▼]    │ …        │
└───────────┴─────────┴───────────────┴────────────┴──────────┘
```

Notes:
- Category should be editable even if symbol is not currently held (Universe page).

---

### 6.2 Settings → Risk Profiles

```text
┌─────────────────────────────┐
│ Risk Profiles               │
├─────────────────────────────┤
│ CNC_Swing_Default   [Edit]  │
│ MIS_Intraday_Cons   [Edit]  │
│ ETF_Swing_Def       [Edit]  │
│ + Create Profile            │
└─────────────────────────────┘
```

---

### 6.3 Risk Profile Editor (Product-aware)

```text
Product: [ CNC ▼ ]

Position Sizing
- Capital / Trade: 30000
- Max Positions: 10
- Max Exposure %: 30

Per-Trade Risk
- Risk % (of equity): 0.075
- Hard Risk %: 0.10

Daily Limits
- Daily Loss %: 0.75
- Hard Daily Loss %: 1.0
- Max Loss Streak: 3

Drawdown
- Mode: [ From Settings by Category ▼ ]

Time Controls
- Force Exit Time: --:--

[ Save ]
```

---

### 6.4 Settings → Drawdown Thresholds (by Product + Category)

```text
Drawdown Thresholds

           CAUTION   DEFENSE   HARD STOP
CNC  LC       6%       9%        12%
CNC  MC       9%      14%        18%
CNC  SC      12%      18%        25%

MIS  LC       2%      3.5%        5%
MIS  MC      2.5%      4%         6%
MIS  SC       3%       5%         7%

[ Save ]
```

---

### 6.5 Alert Intake Log (Decision Transparency)

```text
ALERT RECEIVED
Symbol: ANANTRAJ
Strategy: TrendSwing_v1
Product hint (TV): CNC

Resolved:
- Product: CNC
- Risk Profile: CNC_Swing_Default
- Category (from Holdings): SC
- Drawdown State (CNC+SC): CAUTION

Action: ORDER PLACED
- Capital reduced: 30k → 21k
```

Or:
```text
Action: BLOCKED
Reason: Drawdown HARD STOP (CNC+SC)
```

## 7. Implementation Phases

### Phase 1 – Data Model & Config (MVP-friendly)
- Add `RiskProfile` entity
- Add `SymbolRiskCategory` (LC/MC/SC/ETF) stored per symbol
- Add `DrawdownThresholds` settings table/config keyed by (product, category, state)
- Add `EquitySnapshot` table (daily + intraday optional)

### Phase 2 – Product-Specific Alert → Order
- Extend alert schema to accept optional `product_hint` (CNC/MIS)
- Resolve product by:
  1) RiskProfile default for strategy/source
  2) Override by `product_hint` if allowed
- Derive final product-specific order fields (order type, validity, etc.)

### Phase 3 – Risk Engine Enforcement
- Centralize enforcement in `execute_order_internal()`
- Enforce product-specific constraints:
  - max positions per product
  - max exposure per product
  - per-trade risk
  - daily loss limits
  - loss streak limits
- Add leverage-aware sizing hooks (see Phase 4)

### Phase 4 – MIS / Intraday Extensions (bounded but profitable)
Add MIS-specific controls (new fields on RiskProfile; defaults conservative):
- **Entry cutoff time** (e.g., no new entries after 15:00)
- **Force square-off time** (e.g., 15:20)
- **Max trades/day** and **max trades/symbol/day** (intraday)
- **Min bars between trades** and **cooldown after loss**
- **Slippage guard** (reject if LTP deviates > X bps from trigger)
- **Gap guard** (reject if opening gap exceeds X%)
- **Order-type policy** (market vs limit vs stop-limit)

### Phase 5 – Automatic Leverage Calculations
Goal: size safely under MIS leverage without manual math.

Implementation options:
1) **Broker margins API** (preferred): compute effective leverage from required margin per order.
2) **Static leverage table** (fallback): per symbol/segment default leverage.

Sizing approach:
- Convert risk budget (₹) into quantity using stop distance:
  - `qty = floor(risk_rupees / stop_rupees_per_share)`
- Then cap qty by leverage/margin constraints:
  - ensure required margin ≤ allocated capital budget

Add settings:
- leverage_mode: AUTO (broker) | STATIC | OFF
- max_effective_leverage (hard cap)
- max_margin_used_pct (portfolio-level)

### Phase 6 – Drawdown Implementation
MVP order:
1) **Portfolio-level drawdown** (peak-to-valley) → state machine → throttle/block
2) **Category-level drawdown** (optional v2) using symbol categories

Integrate drawdown checks into risk engine:
- For each alert, read symbol category
- Load drawdown thresholds for (product, category)
- Compute current drawdown state
- Apply throttles/blocking accordingly

### Phase 7 – UI & Observability
- Holdings/Universe category editor (LC/MC/SC)
- Risk Profiles CRUD
- Drawdown thresholds editor
- Alert decision log (placed/blocked + reasons)

### Phase 8 – Testing & Safety
- Unit tests for:
  - product resolution (default + hint)
  - leverage sizing math
  - drawdown state transitions
  - enforcement invariants (no bypass)
- Scenario tests:
  - choppy market (many losses)
  - strong trend (wins)
  - event day (gaps)

## 8. Outcome

With these refinements, SigmaTrader will:

- Keep **strategies clean and reusable**
- Assign drawdown identity at **symbol level**
- Centralize drawdown limits in **settings**
- Apply **product-specific (CNC / MIS) risk profiles**
- Perform **automatic leverage-aware sizing** for MIS
- Prevent misuse of leverage
- Scale safely to intraday trading later

This design improves **correctness, flexibility, and safety** without over-complicating strategies.

---

_End of document_

