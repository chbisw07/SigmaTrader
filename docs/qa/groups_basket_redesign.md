# QA Checklist - Basket Redesign (S32/G02)

Scope: `MODEL_PORTFOLIO` (Basket) only, behind `FEATURE_GROUPS_REDESIGN`. Weight mode only. No execution/buy flow.

## Setup
- Groups redesign is enabled by default. To temporarily disable for comparison/testing, use `?feature_groups_redesign=0` on the app URL.
- Create or select a Basket group (`MODEL_PORTFOLIO`) in the Groups page.

## Basket Builder Dialog
- Open the basket builder from the basket detail panel.
- Funds + mode:
  - Enter Funds (INR) and confirm Mode is Weight (disabled selector).
- Members:
  - Add symbols via quick add (single + paste list).
  - Remove a symbol and confirm it disappears after refresh.
- Weights + locks:
  - Default weights: when a basket has no saved weights yet, opening the builder auto-equalizes weights across all members (until you manually edit weights).
  - Edit weights; confirm "Weights sum" updates.
  - Toggle Lock on one row and run `Equalize` / `Normalize unlocked`; confirm locked weight stays fixed.
  - Use `Clear unlocked`; confirm unlocked weights go to 0.
- Validation:
  - Confirm Save is blocked unless weights sum to 100% and funds are valid.

## Quotes + Summary
- Confirm Live price (LTP) is shown for rows when market data is available.
- Confirm planned Qty/Cost update when LTP changes.
- Confirm the summary shows Planned cost and Remaining.

## Freeze Prices
- Click `Freeze prices`:
  - Confirm `Frozen` timestamp appears.
  - Confirm each row gets a Frozen price (and Δ vs live updates).
- Click `Freeze prices` again:
  - Confirm Frozen prices overwrite with the new snapshot.
- Refresh the page and re-open the basket:
  - Confirm frozen timestamp and frozen prices persist.

## Regression Checks (Non-Negotiable)
- With the flag OFF, basket behavior remains unchanged (legacy UI still works; Allocate has been removed from Groups).
- Watchlist redesign remains unchanged.
- Import flows (`/api/groups/import/watchlist` and related UI) are unchanged.
