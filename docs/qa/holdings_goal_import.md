# Holdings Goal View CSV Import QA Checklist

## Setup
- Have at least 5 holdings in broker holdings.
- Prepare a CSV with columns: Symbol, Label, ReviewDate, Target, Note.

## Upload + Preview
- Open Goal View -> Import CSV.
- Upload CSV; preview shows headers + first 10 rows.

## Mapping
- Map Symbol column (required).
- Optionally map Exchange, Label, Review Date, Target Value, Note.
- Select Target Type when Target Value column is set.
- Set Default label + Default review days.
- Save preset with a name; confirm it appears in preset list.
- Load preset and verify mapping fields update.
- Delete preset; ensure it disappears.

## Import Summary
- Import shows matched/created/updated/skipped counts.
- If symbols not in holdings, they show as skipped with reason `not_in_holdings`.
- Invalid labels show reason `invalid_label:<LABEL>`.
- Invalid target values show reason `invalid_target_value`.

## Post-import
- Goal View reflects new goals without manual refresh.
- Missing goals count decreases accordingly.
