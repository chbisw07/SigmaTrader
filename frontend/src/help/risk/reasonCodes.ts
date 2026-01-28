import type { ReasonCodeEntry } from './types'

export const RISK_REASON_CODES: ReasonCodeEntry[] = [
  {
    code: 'REJECTED_RISK',
    title: 'Order rejected by SigmaTrader risk controls',
    whenItHappens:
      'SigmaTrader blocks an execution attempt before submitting the order to the broker/paper engine.',
    whereYouSeeIt: [
      'Orders table: Status = REJECTED_RISK and an Error message.',
      'Queue/Waiting orders: execution attempt returns “blocked” with a reason code.',
      'System Events: category=risk with details about the block.',
    ],
    whatToDo: [
      'Open the Error field and read the reason code/message.',
      'Adjust your Risk policy settings or the order parameters (qty/product/stop).',
      'Retry execution after the condition clears (e.g., cooldown ends, pause expires).',
    ],
  },
  {
    code: 'RISK_POLICY_TRADE_FREQ_MAX_TRADES',
    title: 'Max trades per symbol/day reached',
    whenItHappens:
      'Trade frequency enforcement blocks an entry when the per-day trade cap for the scope key is already reached.',
    whereYouSeeIt: ['Orders error message / API error detail'],
    whatToDo: [
      'Wait for the next trading day (IST midnight reset).',
      'Increase the limit, or reduce entries for that symbol/strategy/product.',
    ],
  },
  {
    code: 'RISK_POLICY_TRADE_FREQ_MIN_BARS',
    title: 'Min bars between trades not satisfied',
    whenItHappens:
      'Trade frequency enforcement blocks an entry when it happens too soon after the last entry for the same scope key.',
    whereYouSeeIt: ['Orders error message / API error detail'],
    whatToDo: [
      'Wait until enough bars (time-derived) have elapsed for the configured interval.',
      'Reduce the Min bars value if it is too strict for your strategy cadence.',
    ],
  },
  {
    code: 'RISK_POLICY_TRADE_FREQ_COOLDOWN_LOSS',
    title: 'Cooldown after loss is active',
    whenItHappens:
      'A previous closed trade for the scope key was a loss and the cooldown window (in bars) has not elapsed yet.',
    whereYouSeeIt: ['Orders error message / API error detail'],
    whatToDo: [
      'Wait until the cooldown window ends.',
      'Reduce the Cooldown value if it is too strict for your strategy cadence.',
    ],
  },
  {
    code: 'RISK_POLICY_PAUSED',
    title: 'Trading paused for this scope key',
    whenItHappens:
      'Loss controls have put this scope key into a pause window. Entries are blocked until the pause expires.',
    whereYouSeeIt: ['Orders error message / API error detail'],
    whatToDo: [
      'Wait until pause ends (EOD means until the end of the IST day).',
      'Consider lowering max_consecutive_losses or disabling pause_after_loss_streak if desired.',
    ],
  },
  {
    code: 'RISK_POLICY_LOSS_STREAK_PAUSE',
    title: 'Paused after loss streak',
    whenItHappens:
      'Consecutive losses reached the configured threshold and the system applied an EOD pause.',
    whereYouSeeIt: ['Orders error message / API error detail'],
    whatToDo: ['Wait until the next IST day or adjust Loss controls settings.'],
  },
  {
    code: 'RISK_POLICY_CONCURRENT_EXECUTION',
    title: 'Concurrent execution blocked (safety guard)',
    whenItHappens:
      'Two executions for the same scope key arrive at the same time; SigmaTrader serializes them to prevent racing past caps. If it cannot acquire the lock quickly, the request returns as “busy”.',
    whereYouSeeIt: ['Orders error message / API error detail'],
    whatToDo: [
      'Retry after the other execution finishes (usually a few seconds).',
      'If it happens frequently, reduce burst executions for the same symbol/strategy/product or increase min bars between trades.',
    ],
  },
]

export const EXECUTION_POLICY_INTERVAL_SOURCES = [
  'tv_payload',
  'alert_rule',
  'persisted',
  'default_fallback',
] as const
