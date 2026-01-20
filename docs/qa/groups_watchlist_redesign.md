# QA Checklist — Watchlist Redesign (S32 / G01)

Precondition:
- Enable `FEATURE_GROUPS_REDESIGN` for testing (e.g. `?feature_groups_redesign=1` on the Groups page URL).

## Create + Basic Use
- Create a new `WATCHLIST` group from `frontend/src/views/GroupsPage.tsx`.
- Select the watchlist and confirm the new quick-add bar appears (Exchange selector + “Add symbols” input).

## SymbolQuickAdd
- Press `/` anywhere on the page (not in an input) and confirm focus moves to “Add symbols”.
- Add a single symbol with Enter (e.g. `TCS`) and confirm it appears instantly.
- Paste 30–50 symbols (comma/newline separated) and confirm:
  - UI remains responsive while the request runs.
  - Duplicates are skipped (no hard error).
  - Invalid/unknown symbols are skipped with feedback.
- Paste with prefixes (e.g. `NSE:HDFCBANK`, `BSE:500180`) and confirm exchange is respected.

## Watchlist Grid
- Confirm **Notes column is not shown** for watchlists.
- Confirm `LTP` shows for each row and updates via polling.
- Confirm `Day %` shows (or `—` if unavailable).
- Remove a symbol and confirm it disappears and member count updates.

## Regression Checks
- With the flag disabled, Groups page behaves exactly as before for watchlists.
- For non-watchlist group kinds, the legacy UI remains unchanged (no new basket/portfolio behavior introduced in this phase).
- Import flows are unchanged (no changes to watchlist import dialog or endpoints).

