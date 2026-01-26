# TradingView Alert Payload Builder – Requirements & Design

## 1. Purpose

This document defines the requirements, data model, and UX design for a **TradingView Alert Payload Builder** inside SigmaTrader.

The goal is to:
- Eliminate fragile, handwritten JSON in TradingView alerts
- Standardize alert message structure
- Keep **Strategy logic clean** and **risk logic centralized in SigmaTrader**
- Allow **safe flexibility** via dynamic name–value pairs
- Produce a **copy‑paste ready JSON payload** compatible with TradingView strategy alerts

This feature directly follows TradingView’s official alert message guidance:
https://in.tradingview.com/support/solutions/43000481368-strategy-alerts/

---

## 2. Design Principles

1. **Alerts are signals, not orders**  
   TradingView communicates intent; SigmaTrader decides execution.

2. **Schema over free text**  
   Users should build alerts via structured inputs, not raw JSON typing.

3. **Strategy stays clean**  
   No risk rules, sizing, or drawdown logic embedded in strategy.

4. **Flexibility without authority**  
   User‑defined fields are treated as *hints* and may be overridden.

5. **Immediate feedback**  
   JSON preview updates live as fields are edited.

---

## 3. Alert Message Structure

The generated payload is always valid JSON with **three logical blocks** and explicit versioning:

```json
{
  "meta": { ... },
  "signal": { ... },
  "hints": { ... }
}
```

> **Important:** This builder produces *signals*, not executable orders. Any field related to quantity, risk, drawdown, leverage, or stops is treated as **informational only** by SigmaTrader and may be ignored.

---

## 4. Payload Sections

### 4.1 `meta` (System‑Required, Locked)

Purpose: authentication, source identification, versioning.

Characteristics:
- Always present
- Cannot be deleted or renamed
- Values injected automatically by SigmaTrader

Example:

```json
"meta": {
  "secret": "{{SECRET}}",
  "platform": "TRADINGVIEW",
  "version": "1.0"
}
```

Notes:
- `secret` is masked in UI but copied correctly
- Supports secret via JSON body or HTTP header

---

### 4.2 `signal` (Trading Intent – Required)

Purpose: convey *what* TradingView detected, with **stable identifiers**.

Characteristics:
- Predefined keys
- Mandatory identifiers are stable (IDs, not names)
- Defaults use TradingView placeholders
- Users may override values with constants if needed

Default fields:

```json
"signal": {
  "strategy_id": "DUAL_MA_VOL_REENTRY_V1",
  "strategy_name": "Dual MA + Volatility-Adaptive Exits + Trend Re-entry",
  "symbol": "{{ticker}}",
  "exchange": "{{exchange}}",
  "side": "{{strategy.order.action}}",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "timestamp": "{{timenow}}",
  "order_id": "{{strategy.order.id}}"
}
```

Rules:
- `strategy_id` is the **only authoritative identifier** used by SigmaTrader
- `strategy_name` is informational (for logs/UI only)
- Field keys are fixed (no renaming)

---

### 4.3 `hints` (Flexible, User‑Defined, Non‑Authoritative)

Purpose: provide **informational hints only**. These fields **must not** influence risk, sizing, or drawdown decisions.

Characteristics:
- Fully optional
- Arbitrary key–value pairs
- Typed inputs (string, number, boolean, enum)
- SigmaTrader may ignore or override

**Explicit rule:**
- Any risk‑bearing key (quantity, risk %, capital, drawdown, stop‑loss, leverage, etc.) is ignored or rejected.

Example:

```json
"hints": {
  "note": "Breakout above resistance",
  "tag": "trend",
  "tv_quantity": {{strategy.order.contracts}}
}
```

Notes:
- `tv_quantity` (or similar) is treated as *informational only*
- No execution authority is granted to hints

---

## 5. UX Requirements

### 5.1 Location

`Settings → TradingView Webhook → Alert Payload Builder`

---

### 5.2 High‑Level Layout

```text
┌──────────────────────────────────────────────┐
│ TradingView Alert Payload Builder            │
├──────────────────────────────────────────────┤
│ Template name: [ TrendSwing_CNC ]            │
├───────────────┬──────────────────────────────┤
│ Field Builder │ Live JSON Preview             │
│               │ (read‑only, copyable)         │
└───────────────┴──────────────────────────────┘

[ Copy JSON ]   [ Save Template ]   [ Reset ]
```

---

### 5.3 Meta Section (Read‑Only)

```text
META (required)
✔ secret       {{SECRET}}   (locked)
✔ platform     TRADINGVIEW (locked)
✔ version      1.0         (locked)
```

---

### 5.4 Signal Section (Predefined Fields)

```text
SIGNAL

✔ strategy_id    [ TrendSwing_v1 ]
✔ symbol         [ {{ticker}} ]
✔ exchange       [ {{exchange}} ]
✔ side           [ {{strategy.order.action}} ]
✔ price          [ {{close}} ]
✔ timeframe      [ {{interval}} ]
✔ timestamp      [ {{timenow}} ]
```

Features:
- Checkbox = include/exclude (if optional)
- Mandatory fields cannot be disabled
- Tooltips explain TradingView placeholders

---

### 5.5 Hints Section (Dynamic Key–Value Builder)

```text
HINTS (optional, informational only)

Key              Type     Value
──────────────────────────────────────
note             string   Breakout setup
tag              string   trend
tv_quantity      number   {{strategy.order.contracts}}

[ + Add Field ]
```

Rules:
- Keys must be unique
- Keys validated (no spaces, JSON‑safe)
- Type‑aware inputs
- UI explicitly warns: "Hints do not control risk or execution"

---

### 5.6 Live JSON Preview

- Updates instantly on any change
- Read‑only
- Secret masked visually
- One‑click copy

---

## 6. Template Management

Optional but recommended:

- Save multiple payload templates
- Reuse across alerts
- Example templates:
  - `TrendSwing_CNC`
  - `TrendSwing_MIS`
  - `GoldETF_Swing`

---

## 7. Validation & Safety

UI‑level validation:
- Missing required fields
- Invalid keys or types
- Warning if user attempts to add reserved execution/risk keys

Runtime behavior:
- SigmaTrader treats hints as **advisory only**
- Quantity, sizing, and risk hints are ignored or logged
- All risk enforcement is implemented exclusively inside SigmaTrader

---

## 8. Benefits

- Zero JSON syntax errors
- Faster alert creation
- Consistent alert contracts
- Cleaner strategy design
- Safer AUTO mode execution
- Scales naturally to future features

---

## 9. Out of Scope (for this feature)

- Editing TradingView strategies
- Executing trades directly from UI
- Risk enforcement logic (handled elsewhere)

---

_End of document_

