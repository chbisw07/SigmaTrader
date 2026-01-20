# Groups, Watchlists, Baskets & Portfolios – Redesign PRD

## 1. Purpose & Context
This document defines the **end‑to‑end redesign** of the **Groups** system in SigmaTrader / SigmaQLab, covering:
- Watchlists
- Baskets (pre‑execution allocation templates)
- Portfolios (executed baskets)

The goal is to create a **fast, intuitive, allocation‑correct, and reusable** system that:
- Minimizes friction when creating watchlists
- Makes basket creation mathematically correct and UX‑safe
- Cleanly separates *intent* (basket) from *execution* (portfolio)
- Can be reused across other parts of the app (Backtests, Allocate, Rebalance, Universe selectors)

This document is intended to be a **single source of truth** for:
- Product understanding
- UX flows
- Allocation logic
- Backend contracts
- Implementation reference for Codex

---

## 2. Core Mental Model

### 2.1 Group Types
| Type | Meaning | Mutable? | Price Reference | Execution |
|---|---|---|---|---|
| Watchlist | Symbols for tracking | Yes | Live LTP | No |
| Basket | Allocation template | Yes | Frozen + Live | No |
| Portfolio | Executed holdings | Limited | Buy Avg + Live | Yes |

### 2.2 Lifecycle
```
Watchlist → (optional) Basket → Buy → Portfolio
```
- **Watchlist**: discovery & monitoring
- **Basket**: capital + allocation planning
- **Portfolio**: actual holdings created from basket execution

---

## 3. Groups Page – High‑Level Layout

### 3.1 Left Panel: Groups List
Reusable across all group types.

**Features**:
- Tabs / filters: All | Watchlists | Baskets | Portfolios
- Search by name
- Sort: Updated | Name | Members
- Quick actions: Edit | Duplicate | Export | Delete

**Row fields**:
- Name
- Type chip
- Members count
- Updated timestamp

---

### 3.2 Right Panel: Group Details (Context‑Aware)

#### Header
- Group Name
- Group Type chip
- Metadata: Created, Updated
- Primary Actions (vary by type)

| Type | Actions |
|---|---|
| Watchlist | Open in Grid, Export |
| Basket | Edit Basket, Buy Basket, Open in Grid |
| Portfolio | Open, Rebalance, Add Funds |

---

## 4. Watchlist PRD

### 4.1 Goals
- Extremely fast symbol entry
- Minimal cognitive load
- Market context visibility

### 4.2 Symbol Entry (Critical UX)

**Symbol Quick Add Bar**:
- Autocomplete (NSE/BSE toggle)
- Supports:
  - Single symbol + Enter
  - Paste comma / newline separated symbols
  - NSE:HDFCBANK, BSE:500180

**Keyboard shortcuts**:
- `/` → focus input
- `Enter` → add symbol
- `Ctrl+V` → bulk paste

Duplicate and invalid symbols are skipped with feedback.

---

### 4.3 Watchlist Grid Columns
| Column | Notes |
|---|---|
| Symbol | Read‑only |
| Exchange | Read‑only |
| Last Price (LTP) | Read‑only, live |
| Day % (optional) | Read‑only |
| Actions | Remove |

**Removed**: Notes column

---

## 5. Basket PRD (Core Feature)

### 5.1 Basket Definition
A **Basket** represents:
- Capital intent (Funds)
- Allocation rule (Mode)
- Symbol set
- Frozen reference prices

It is **not executed** until explicitly bought.

---

### 5.2 Basket Creation Flow
1. Create Basket → Name + Exchange
2. Open **Basket Builder Dialog**
3. Configure funds + allocations
4. Freeze prices
5. Save basket

---

## 6. Basket Builder Dialog – Wireframe (Logical)

```
┌──────────────────────────────────────────────┐
│ Basket Builder                               │
├──────────────────────────────────────────────┤
│ Funds: ₹ [ 100000 ]   Mode: [ Weight ▼ ]    │
│ Price Source: Live LTP | Frozen at: 20:34    │
│ [ Freeze Prices Now ]                        │
├──────────────────────────────────────────────┤
│ Symbol | LTP | Frozen | Δ% | Weight | Amt | │
│        |     |        |    | 🔒 25   | ... | │
│        |     |        |    | 🔓 25   | ... | │
│----------------------------------------------│
│ Equalize | Normalize Unlocked | Clear        │
├──────────────────────────────────────────────┤
│ Members: 4                                  │
│ Basket Cost Now: ₹ 98,420                   │
│ Remaining Cash: ₹ 1,580                    │
│ Validation: OK                              │
├──────────────────────────────────────────────┤
│ Cancel                     Save Basket      │
└──────────────────────────────────────────────┘
```

---

## 7. Allocation Modes

### 7.1 Common Columns
Always visible:
- Symbol
- Exchange
- Live Price (LTP)
- Frozen Price
- Δ since freeze (₹, %)
- Lock toggle
- Remove action

---

### 7.2 Weight Mode (Default)

**Editable**:
- Weight %

**Computed**:
- Amount = Funds × Weight%
- Qty = floor(Amount / LTP)
- Cost Now = Qty × LTP

#### Lock Semantics
- 🔒 Locked row: weight fixed
- 🔓 Unlocked row: auto‑adjustable

#### Auto Distribution
```
Remaining = 100 − Σ(locked) − Σ(manual unlocked)
Distribute equally among remaining unlocked rows
```

#### Actions
- Equal weights
- Normalize unlocked (preserve locks)
- Clear unlocked

**Validation**:
- Total weight must equal 100 before Buy

---

### 7.3 Amount Mode

**Editable**:
- Amount per symbol

**Computed**:
- Weight % = Amount / Funds
- Qty = floor(Amount / LTP)

**Lock**:
- Locked amount remains fixed
- Remaining funds distributed among unlocked rows

**Validation**:
- Total amount ≤ Funds

---

### 7.4 Qty Mode

**Editable**:
- Qty

**Computed**:
- Amount = Qty × LTP
- Weight % = Amount / Funds

**Validation**:
- Total cost now ≤ Funds (or explicit override)

---

## 8. Price Freezing & Live Comparison

Each basket stores:
- `frozen_price` per symbol
- `frozen_at` timestamp

UI shows:
- Frozen Price
- Live LTP
- Δ % / Δ ₹

Basket always shows:
- **Fresh Basket Cost Now** = Σ(Qty × LTP)

---

## 9. Buy Basket → Portfolio Flow

### 9.1 Buy Preview Dialog

Shows:
- Basket metadata
- Estimated cost now
- Per‑symbol planned qty

Options:
- Product (CNC/MIS)
- Order type (MARKET default)
- Safety buffer (optional)

---

### 9.2 Portfolio Creation

Portfolio stores:
- Executed qty
- Avg buy price
- Buy timestamp
- Reference basket ID
- Frozen prices snapshot

Basket remains reusable.

---

## 10. Reusability & Architecture

### 10.1 Reusable Components
- GroupListPanel
- SymbolQuickAdd
- MembersGrid (mode‑aware)
- BasketBuilderDialog
- BuyPreviewDialog

### 10.2 Allocation Engine (Critical)
Single pure function:

Inputs:
- Funds
- Mode
- Symbols (ltp, locks, user inputs)

Outputs:
- Qty / Amount / Weight per row
- Basket totals
- Validation errors

Used by:
- Basket creation
- Portfolio rebalance (future)
- Allocation features elsewhere

---

## 11. MVP Scope

### Phase 1 (Must‑Have)
- Watchlist fast add + LTP
- Basket with Weight mode
- Locks + normalize
- Price freeze
- Buy basket → portfolio

### Phase 2
- Amount & Qty modes
- Advanced buy controls
- Portfolio rebalance

---

## 12. Non‑Goals
- No advanced order slicing (v1)
- No tax / brokerage modeling (v1)

---

## 13. Success Criteria
- Watchlist creation < 10 seconds
- Basket allocation always mathematically valid
- No silent capital mismatch
- Same logic reusable across app

---

**This document is authoritative for both product decisions and implementation.**

