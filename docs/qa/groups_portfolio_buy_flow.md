# QA Checklist - Portfolio Buy Flow (S32/G03)

Scope: Buy a Basket (`MODEL_PORTFOLIO`) into a Portfolio (`PORTFOLIO`), behind `FEATURE_GROUPS_REDESIGN`. Creates queued orders; execution/risk policies remain unchanged.

## Setup
- Groups redesign is enabled by default. To temporarily disable for comparison/testing, use `?feature_groups_redesign=0`.
- Ensure DB is migrated through head (includes `0057_add_portfolio_origin_snapshot.py`).
- Create/select a Basket with members and saved weights/funds.
- Freeze basket prices (required).

## Buy Preview Dialog
- Open Groups → select the Basket → click `Buy basket → portfolio`.
- Confirm:
  - Shows Funds, estimated cost now, remaining.
  - Shows per-symbol LTP, Frozen price, planned qty and estimated cost.
  - Blocks buy when basket is not frozen or when weights/funds are invalid.
- Create portfolio + orders:
  - Click `Create portfolio + orders`.
  - Confirm a new Portfolio group is created and selected.

## Backend/DB Invariants
- Portfolio group fields:
  - `origin_basket_id` points to the basket used.
  - `bought_at` is set.
  - `frozen_at` matches the basket’s frozen timestamp.
- Portfolio members:
  - Same symbol/exchange membership as the basket.
  - `frozen_price` copied from basket snapshot for traceability.
- Orders:
  - Created as `WAITING`.
  - `orders.portfolio_group_id` equals the new portfolio group id.
  - Side is `BUY`.

## Post-buy UX / Execution
- Orders appear in Queue/Orders (manual workflow).
- After executing orders and syncing, portfolio holdings update via existing order sync:
  - `reference_qty` and `reference_price` reflect executed qty and avg buy price (from execution, not frozen price).
- Basket remains unchanged and reusable (can re-freeze and buy again).

## Regression Checks (Non-Negotiable)
- With the flag OFF, existing basket/portfolio behavior is unchanged.
- Watchlist redesign remains unchanged.
- Import flows are unchanged.
