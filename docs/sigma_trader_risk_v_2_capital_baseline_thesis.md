# SigmaTrader Risk Engine v2 — Capital-Aware, Reality-Aligned Trading

> **Purpose**: This document is the canonical thesis for the revised SigmaTrader risk model.  
> It explains *why* the change is needed, *what* conceptual model is adopted, *how* it blends into the current Risk v1/v2 unification, and *how* it should be implemented across backend, APIs, and UX.

This is written to serve **two audiences simultaneously**:
- **You (the operator / trader)** — to get a complete, end-to-end mental picture by reading once.
- **Codex (the implementer)** — to translate directly into schemas, APIs, execution logic, and UI.

---

## 1. Problem Statement — Why Risk v1 Is Not Enough

Most retail algo systems (and many broker tools) treat **"capital"** as a single number:

- equity
- balance
- net liquidation value
- notional capital

This abstraction works only in *toy models*.

In **real trading**, capital is split across *different economic roles*:

- **Cash** → enables **BUYs**
- **Holdings / Positions** → enable **SELLs**

Using one baseline for both leads to:
- accidental over-selling long-term holdings
- risk rules that look correct but fail in live markets
- inability to protect capital intentionally

SigmaTrader Risk v2 explicitly **rejects the single-baseline model**.

---

## 2. Core Insight — Capital Has Roles, Not Just Quantity

### 2.1 Two Fundamental Capital Pools

SigmaTrader recognizes **two independent baselines**:

| Capital Pool | Source of Truth | Used For |
|-------------|----------------|----------|
| **Cash Baseline** | Broker available cash / margin | BUY sizing, drawdowns, exposure |
| **Holdings Baseline** | Broker holdings & open positions | SELL sizing, protection |

These are **orthogonal** and must never be conflated.

> A BUY must never be sized from holdings value.  
> A SELL must never be sized from cash value.

---

## 3. Capital Allocation — From Raw Capital to Tradable Capital

Raw capital is **not automatically tradable capital**.

SigmaTrader introduces *allocation policies* that decide what portion of capital is *eligible* for automation.

### 3.1 Cash Allocation (BUY-side Protection)

Not all broker cash should be exposed to automation.

#### Concept
- A portion of cash is **reserved**
- Only remaining cash is used for BUY sizing

#### Global Setting

```
Cash reserve ratio: 40%
```

#### Derived Values

```
broker_cash = ₹200,000
reserved_cash = ₹80,000
usable_cash = ₹120,000
```

All BUY-side risk rules apply **only** to `usable_cash`.

This protects:
- emergency liquidity
- manual discretionary trades
- drawdown spirals

---

### 3.2 Holdings Allocation (SELL-side Protection)

Holdings are often mixed:
- long-term investments
- swing trades
- tactical positions

Risk engines must **not assume all holdings are sellable**.

#### Concept
Each holding is split into:

- **Locked Qty** → never auto-sold
- **Active Qty** → eligible for automated SELLs

```
active_qty = total_qty − locked_qty
```

#### Global Default

```
Default locked ratio (CNC): 50%
```

Used only when:
- a symbol is first introduced
- no explicit override exists

#### Per-Symbol Override (Authoritative)

```
Symbol: INFY
Total qty: 200
Locked qty: 120
Active qty: 80
```

Per-symbol locked qty always **wins over global ratios**.

---

## 4. Order Sizing Semantics (Deterministic & Predictable)

### 4.1 BUY Orders

| Product | Baseline Used |
|-------|---------------|
| CNC BUY | Usable cash (after reserve) |
| MIS BUY | Available margin |

Example:

```
Usable cash = ₹120,000
Max order % = 20%
Order value ≤ ₹24,000
```

---

### 4.2 SELL Orders

| Product | Baseline Used |
|-------|---------------|
| CNC SELL | Active quantity only |
| MIS SELL | Open position quantity |

Example (CNC):

```
Total qty = 200
Locked qty = 100
Active qty = 100
Sell % = 50%
Final sell qty = 50
```

This ensures:
- long-term holdings are protected
- sell percentages behave intuitively

---

## 5. Relationship With Existing Risk Controls

**Important**: This model does NOT replace existing risk rules.

It defines **what pool those rules apply to**.

### 5.1 What Stays Unchanged

- Drawdown thresholds
- Max order %
- Max qty
- Trade frequency limits
- CNC vs MIS profiles
- Source overrides

### 5.2 Execution Order (Conceptual)

```
1. Fetch broker state (cash, holdings, positions)
2. Apply cash reserve
3. Apply locked qty rules
4. Select correct baseline (BUY vs SELL)
5. Apply existing risk constraints
6. Finalize qty / value
7. Place order
```

---

## 6. UX Integration — Minimal, Explicit, Trust-Building

### 6.1 Risk Settings Page (Additive Changes)

```
┌────────────────────────────┐
│ Risk Globals               │
│ ✓ Enable risk enforcement  │
│                            │
│ Capital baselines (auto):  │
│ • Cash → BUY               │
│ • Holdings → SELL          │
└────────────────────────────┘

┌────────────────────────────┐
│ Capital Allocation         │
│ Cash reserve: [40%]        │
│ Default locked qty: [50%]  │
└────────────────────────────┘
```

No manual baseline equity input remains.

---

### 6.2 Holdings Page (Critical Visibility)

```
┌────────┬──────────┬──────────┬──────────┐
│Symbol  │ Total Qty│ Locked   │ Active   │
├────────┼──────────┼──────────┼──────────┤
│INFY    │ 200      │ [120]    │ 80       │
│TCS     │ 100      │ [50]     │ 50       │
└────────┴──────────┴──────────┴──────────┘
```

- Locked qty is editable
- Active qty is computed

---

### 6.3 Execution Preview (Confidence Layer)

BUY preview:
```
Cash baseline used: ₹120,000
Reserved: ₹80,000
```

SELL preview:
```
Holdings: 200
Locked: 120
Active: 80
Sell qty: 40
```

---

## 7. Backend Data Model (Conceptual)

### 7.1 New Global Settings

```json
{
  "cash_reserve_ratio": 0.40,
  "default_locked_ratio_cnc": 0.50
}
```

### 7.2 Per-Symbol State

```json
{
  "symbol": "INFY",
  "locked_qty": 120
}
```

Derived fields are never persisted:
- active_qty
- usable_cash

---

## 8. Edge Cases & Invariants (Non-Negotiable)

1. locked_qty ≤ total_qty (always clamp)
2. Active qty cannot go negative
3. Partial fills must recompute baselines
4. Multiple queued sells must reserve active qty
5. Corporate actions may require manual locked-qty repair
6. Manual orders may optionally bypass locking (policy-controlled)

---

## 9. Design Philosophy (Why This Scales)

This model is:
- **Capital-aware** (cash ≠ holdings)
- **Role-aware** (BUY vs SELL)
- **Stateful** (per-symbol intent preserved)
- **Human-aligned** (matches trader intuition)

It moves SigmaTrader from *rule execution* to **capital governance**.

---

## 10. Final Mental Model (One-Line Summary)

> *Risk is not about how much capital you have — it is about how much capital you are willing to expose, and to which actions.*

SigmaTrader Risk v2 makes that explicit, enforceable, and boringly reliable.
