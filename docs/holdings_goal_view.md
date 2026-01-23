# Goal View rollout notes

Goal View is a daily review workflow, not a trading signal system. It exists to keep intent visible and force periodic review without forcing trades.

## Guardrails
- No auto-sell or forced actions. The UI only nudges review.
- Alerts are attention cues only (review due/overdue, near target).
- Targets are optional; review dates are mandatory.
- When review date is overdue, near-target cues should be muted until the review is extended.

## Review workflow
- Mark reviewed: resets the review date based on label defaults (CORE/TRADE/etc.).
- Snooze: pushes review date forward from today (or the current review date, whichever is later).
- Extend: pushes review date by a fixed number of days.
- Review history logs every review action with before/after dates.

## Behavior expectations
- Overdue items appear first in filters and are highlighted.
- Due soon items surface in reminders (default: 7 days).
- Near target cues use a global threshold (default: 5%).

## Non-goals (v2)
- No automated trading actions.
- No per-holding alert thresholds.
- No multi-target exit plans.
