# Intent‑Driven Portfolio Management

## 1. Philosophy

### 1.1 The Problem We Are Solving
Traditional portfolio management tools focus on *what you hold* and *how it performed*, but largely ignore *why you bought it* and *how long you intended to hold it*. Over time, this leads to:

- Selling long‑term investments for short‑term needs
- Forgetting the original thesis or time horizon
- Holding positions far longer (or shorter) than intended
- Emotional or reactive decisions disconnected from original intent

The result is not necessarily poor returns, but **poor discipline and poor clarity**.

### 1.2 Core Belief
For an individual investor, **behavioral discipline and intent clarity** matter more than complex quantitative optimization.

The goal is not to predict markets better, but to:
- Remember your own reasoning
- Stay aligned with your timelines
- Make selling decisions consciously, not accidentally

### 1.3 Portfolio as a Living Farm
We treat a portfolio like a farm, not a trading book:

- Each position is planted with a purpose
- Each has an expected growing period
- Crops are reviewed periodically
- Harvesting happens intentionally, not randomly

This philosophy emphasizes *cultivation over speculation*.

---

## 2. The Core Idea: Position Intent

Instead of treating a stock or ETF as a single static holding, we introduce the concept of a **Position Intent**.

A Position Intent captures the *human context* around a buy decision.

### 2.1 What Is a Position Intent?
A Position Intent is metadata attached to a position (or group of buys) that answers:

- Why did I buy this?
- How long did I plan to hold it?
- What should trigger my attention?

This information is lightweight, optional, and non‑enforcing by default.

---

## 3. Minimal Intent Model (Deliberately Simple)

The system intentionally avoids over‑engineering. The following fields deliver maximum value with minimal complexity.

### 3.1 Label (WHY)
A simple label describing the purpose of the position.

Examples:
- Long term
- Short term
- Retirement
- Child education
- Opportunistic
- Temporary / Ad‑hoc

Notes:
- One primary label per intent (initially)
- Free text or preset list
- This becomes the anchor for grouping and review

---

### 3.2 Target Duration / Target Date (WHEN)
Defines the intended holding horizon.

User can specify **either**:
- Target date (e.g., 31 Mar 2027)
- Target duration (e.g., 2y 3m)

Internally normalized to:
- Entry date
- Target date

---

### 3.3 Age (Derived, Read‑Only)
Computed automatically:

- Age = Today − Entry date
- Remaining time = Target date − Today

Displayed in human‑friendly form:
- Held for: 1y 4m
- Remaining: 8 months
- Overdue: 3 months

This creates powerful self‑awareness without judgment.

---

### 3.4 Target Price (Optional)
Defines a price‑based attention trigger.

Supported formats:
- Absolute price (₹1,250)
- Relative change (+25%, −15%)

Important:
- Target price is **advisory**, not an auto‑sell
- Used only for alerts/reminders in MVP

---

### 3.5 Alerts & Reminders (WHEN TO PAY ATTENTION)
Alerts are nudges, not trades.

Examples:
- Review 6 months before target date
- Notify when target price is hit
- Alert on −20% drawdown
- Quarterly review reminder
- Held beyond target duration

Alerts are configurable and non‑mandatory.

---

## 4. What This Enables (Without Quant Complexity)

Even with this minimal model, the system can surface extremely valuable insights:

- Which positions are overdue for review
- How much of the portfolio is truly long‑term vs short‑term
- Which goals generated realized profits
- Patterns of early selling or overstaying positions

All without:
- Factor models
- Correlation matrices
- Optimization solvers
- Mathematical abstractions

---

## 5. MVP Scope (Phase 1)

### 5.1 Core Features

#### Position Intent
- Attach intent metadata to a position
- Editable at any time (with history retained optionally later)

#### Portfolio List View
For each position:
- Symbol
- Label
- Age / Target
- Current PnL
- Status chip:
  - On track
  - Review due
  - Overdue
  - Target hit

---

### 5.2 Position Detail View
- Intent summary
- Timeline bar (Entry → Target → Today)
- Target price
- Alerts configured
- Buy/sell history (existing data)

---

### 5.3 Review Inbox
A simple actionable list:
- “Review HDFCBANK (overdue by 45 days)”
- “Target price hit: NIFTY ETF”
- “Held longer than planned: ABC Ltd”

This becomes the primary interaction surface.

---

## 6. Explicit Non‑Goals (for MVP)

To avoid overkill, the following are explicitly out of scope for MVP:

- Correlation analysis
- Heatmaps
- Factor exposure
- Portfolio optimization
- Automatic trade execution
- Tax optimization

These may be considered later only if they clearly improve decision quality.

---

## 7. Formalized PRD

### 7.1 Objectives
- Preserve user intent over time
- Improve behavioral discipline
- Provide clarity on timelines and goals
- Reduce accidental or emotionally driven decisions

---

### 7.2 Functional Requirements

#### FR‑1: Intent Metadata
- User can create/edit intent for a position
- Fields: label, target date/duration, target price, alerts

#### FR‑2: Derived Age Calculation
- System computes and displays age and remaining time

#### FR‑3: Alerts Engine
- Time‑based alerts
- Price‑based alerts
- Overdue alerts

#### FR‑4: Review Inbox
- Aggregated list of all alerts and overdue reviews

---

### 7.3 Data Model (Simplified)

PositionIntent:
- id
- symbol
- entry_date
- target_date
- label
- target_price (optional)
- alerts[]
- created_at
- updated_at

---

### 7.4 UX Principles
- Minimal input required
- Read‑only derived values clearly marked
- No forced automation
- Emphasis on reminders, not enforcement

---

### 7.5 Success Metrics
- % of positions with intent attached
- % of positions reviewed on or before target date
- Reduction in premature sells (self‑reported)
- User trust and continued usage

---

## 8. Future Extensions (Optional, Non‑Blocking)

- Realized PnL grouped by label
- XIRR per label/goal
- Thesis notes and sell‑reason capture
- Broker reconciliation
- Corporate action handling
- Monthly portfolio diary export

These are deliberately deferred.

---

## 9. Closing Note

This approach prioritizes **clarity over cleverness**.

It treats portfolio management as a long‑term practice, not a mathematical contest. The system exists to help the investor remember, review, and act with intention.

That alone is a durable edge.