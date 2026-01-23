# Holdings Goal View v2 QA

## Review actions
- Open Holdings -> Goal View.
- Pick a holding with a goal.
- Open the actions menu (three dots).
- Click "Mark reviewed"; verify the review date jumps forward based on label defaults.
- Click "Snooze 7d"; verify review date shifts by 7 days from today or current review date (whichever is later).
- Click "Extend 30d" and "Extend 90d"; verify date updates accordingly.
- Open "View history"; verify the review action entries appear with previous/new dates.

## Alerts banner
- Use a goal with a past review date; confirm an overdue banner appears and "View overdue" filters rows.
- Use a goal with review date within 7 days; confirm the due-soon banner appears and filters correctly.
- Use a goal near target (<= 5%); confirm the near-target banner appears and filters correctly.
- Set a review date in the past; confirm the near-target banner count does not include overdue holdings.

## Regression
- Default view still works.
- Goal edit dialog still saves goals.
- CSV import still works and goals display in Goal View.
