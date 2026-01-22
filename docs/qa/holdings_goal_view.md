# Holdings Goal View MVP QA Checklist

## Setup
- Use broker holdings (Zerodha or AngelOne) with at least 3 symbols.
- Ensure some holdings have no goal records.

## Goal View UI
- Switch View -> Goal View.
- Verify columns: Label, Review Date, Days, Status, Target, Away %, Note, Actions.
- Confirm Default View remains unchanged.

## Missing Goals
- Holdings without goals show "No goal" badge.
- "Missing" filter shows only holdings without goals.
- "Set missing goals (N)" opens Edit Goal for the first missing holding.

## Edit Goal
- Label required; defaults to CORE.
- Review date auto-filled based on label; editable.
- Target type optional; target value required only when target type is set.
- Computed target preview updates when target inputs change.
- Save creates/updates the goal and updates the row without reload.

## Status + Filters
- Overdue (review date < today) shows red status and filter works.
- Due Soon (<= 7 days) shows amber status and filter works.
- Near Target (<= 5% away) filter works based on Away %.
- All filter shows full holdings list.

## Quick Actions
- Edit button opens the drawer.
- +30d extends review date and updates Days/Status.

## Error Handling
- Goal API errors show a compact error message above the grid.
- Invalid target input shows an inline error in the drawer.
