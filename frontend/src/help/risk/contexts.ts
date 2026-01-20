import type { HelpContext } from './types'
import { RISK_REASON_CODES } from './reasonCodes'

export const RISK_GUIDE_MANDATORY_TOPIC_IDS = [
  'broker-vs-app',
  'chokepoint',
  'covered-flows',
  'scope-keys',
  'equity-baseline',
  'account-level-limits',
  'per-trade-risk',
  'position-sizing',
  'stop-rules-managed-exits',
  'trade-frequency',
  'loss-controls',
  'interval-bars',
  'day-boundary',
  'blocked-behavior',
  'safety-guarantees',
  'limitations',
] as const

function reasonCodesAsBullets() {
  return RISK_REASON_CODES.map((rc) => `${rc.code}: ${rc.title}`)
}

export const brokerSettingsHelp: HelpContext = {
  id: 'settings-broker',
  title: 'Broker settings help',
  overview: [
    'This tab connects brokers and stores broker credentials (API keys/secrets) used for LIVE execution and market data.',
    'Risk Policy can still block orders before they reach the broker. Broker errors can still happen after submission.',
  ],
  sections: [
    {
      id: 'broker-basics',
      title: 'Basics',
      qas: [
        {
          id: 'broker-which-supported',
          question: 'Which brokers are supported?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader supports Zerodha (Kite) and AngelOne (SmartAPI). Both can be connected.',
            },
          ],
        },
        {
          id: 'broker-live-vs-paper',
          question: 'What is LIVE vs PAPER execution?',
          answer: [
            {
              type: 'p',
              text: 'LIVE submits orders to your connected broker. PAPER simulates execution inside SigmaTrader.',
            },
            {
              type: 'callout',
              tone: 'info',
              text: 'Risk Policy enforcement (blocking/clamping) happens before submission in both LIVE and PAPER paths when enabled.',
            },
          ],
        },
        {
          id: 'broker-product-mis-cnc',
          question: 'What do MIS and CNC mean?',
          answer: [
            {
              type: 'p',
              text: 'MIS is intraday (margin) product. CNC is delivery. Risk Policy can allow/disallow these globally and via overrides.',
            },
          ],
        },
      ],
    },
    {
      id: 'broker-troubles',
      title: 'Common questions',
      qas: [
        {
          id: 'broker-why-market-data-unavailable',
          question: 'Why does it say “Market data unavailable”?',
          answer: [
            {
              type: 'p',
              text: 'Market data availability depends on broker connectivity and instrument mapping. Without market data, some price-based checks may fail.',
            },
          ],
        },
        {
          id: 'broker-what-if-broker-rejects',
          question: 'What if the broker rejects my order?',
          answer: [
            {
              type: 'p',
              text: 'If SigmaTrader submits an order but the broker rejects it, the order will show FAILED with the broker error message (where available).',
            },
          ],
        },
      ],
    },
  ],
  gettingStarted: [
    'Connect Zerodha and/or AngelOne in this tab.',
    'Verify the “connected” badge and market data availability.',
    'Then go to Risk settings to enable enforcement and set guardrails.',
  ],
  troubleshooting: [
    {
      id: 'broker-ts-no-secrets',
      question: 'I cannot connect the broker. What should I check?',
      answer: [
        { type: 'bullets', items: ['Confirm API key/secret are added.', 'Re-login to broker if session expired.', 'Check System Events for broker/auth errors.'] },
      ],
    },
    {
      id: 'broker-ts-order-fails',
      question: 'An order shows FAILED. Where is the reason?',
      answer: [
        {
          type: 'bullets',
          items: [
            'Orders page → Error column (broker error message).',
            'System Events page → category=order for placement failures.',
          ],
        },
      ],
    },
  ],
}

export const marketConfigurationHelp: HelpContext = {
  id: 'settings-market',
  title: 'Market configuration help',
  overview: [
    'This tab controls market session rules (calendar/holidays) and how SigmaTrader treats trading sessions.',
    'Some “per day” risk limits reset based on a timezone boundary (documented below).',
  ],
  sections: [
    {
      id: 'market-day',
      title: 'Trading day & timezone',
      qas: [
        {
          id: 'market-day-boundary',
          question: 'What does “per day” mean for risk limits?',
          answer: [
            {
              type: 'p',
              text: 'For trade frequency and loss controls, SigmaTrader treats “day” as the IST calendar date and resets at midnight IST.',
            },
          ],
        },
        {
          id: 'market-symbol-canonical',
          question: 'How are symbols identified?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader canonicalizes symbols as EXCHANGE:SYMBOL (uppercased). This is used for scoping risk controls.',
            },
          ],
        },
      ],
    },
    {
      id: 'market-session',
      title: 'Sessions & availability',
      qas: [
        {
          id: 'market-hours',
          question: 'Does SigmaTrader block orders outside market hours?',
          answer: [
            {
              type: 'p',
              text: 'LIVE orders are still subject to broker market-hour rules. PAPER execution is gated by SigmaTrader market hours.',
            },
          ],
        },
      ],
    },
  ],
  gettingStarted: [
    'Keep your market calendar updated for the exchange you trade.',
    'Use the preview to verify the session for a given date.',
    'If you rely on PAPER mode, ensure market hours are configured correctly.',
  ],
  troubleshooting: [
    {
      id: 'market-ts-day-mismatch',
      question: 'My “per day” limits reset at a different time than expected.',
      answer: [
        {
          type: 'p',
          text: 'Trade frequency/loss controls reset at midnight IST (calendar date). If you expected a market-open reset, adjust your operational workflow accordingly.',
        },
      ],
    },
  ],
}

export const tradingViewWebhookHelp: HelpContext = {
  id: 'settings-webhook',
  title: 'TradingView webhook help',
  overview: [
    'This tab configures how TradingView alerts are authenticated and routed into SigmaTrader orders.',
    'Risk Policy is enforced at dispatch/execute time (AUTO and manual execution paths).',
  ],
  sections: [
    {
      id: 'tv-auth',
      title: 'Authentication',
      qas: [
        {
          id: 'tv-secret',
          question: 'What is the TradingView webhook secret?',
          answer: [
            {
              type: 'p',
              text: 'TradingView alerts must include the configured secret. SigmaTrader rejects alerts with missing/invalid secrets.',
            },
          ],
        },
      ],
    },
    {
      id: 'tv-routing',
      title: 'Routing & enforcement',
      qas: [
        {
          id: 'tv-manual-vs-auto',
          question: 'What is MANUAL vs AUTO mode?',
          answer: [
            {
              type: 'p',
              text: 'AUTO attempts to dispatch the order immediately. MANUAL converts the alert into a WAITING order in the queue so you can execute it later.',
            },
            {
              type: 'callout',
              tone: 'info',
              text: 'Risk Policy enforcement happens at dispatch/execute time in both modes when Risk policy → Enable enforcement is ON.',
            },
          ],
        },
        {
          id: 'tv-interval-bars',
          question: 'What does “bars” mean for Trade frequency (min bars / cooldown)?',
          answer: [
            {
              type: 'p',
              text: 'Bars are time-derived from an effective interval (minutes). SigmaTrader uses interval information when present and falls back to a default interval when missing.',
            },
            {
              type: 'bullets',
              items: [
                'Interval sources: TradingView payload interval → alert rule timeframe → persisted state → default fallback (5m).',
                'When default fallback is used, SigmaTrader logs a one-time INFO SystemEvent for that scope key.',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'tv-payload',
      title: 'Payload essentials',
      qas: [
        {
          id: 'tv-required-fields',
          question: 'Which payload fields matter for risk enforcement?',
          answer: [
            {
              type: 'bullets',
              items: [
                'st_user_id: which SigmaTrader user to route to.',
                'strategy_name: used for scoping certain risk controls when no strategy/deployment id exists.',
                'symbol/exchange: used to canonicalize EXCHANGE:SYMBOL.',
                'interval (optional): used to interpret “bars” for trade frequency and cooldown.',
                'trade_details: side/qty/price (price may be required for certain risk checks).',
              ],
            },
          ],
        },
      ],
    },
  ],
  gettingStarted: [
    'Set a webhook secret and store it.',
    'Send a test alert from TradingView to verify SigmaTrader receives it.',
    'Choose MANUAL (queue) or AUTO (immediate dispatch) based on your workflow.',
  ],
  troubleshooting: [
    {
      id: 'tv-ts-order-blocked',
      question: 'My TradingView order was blocked. Where do I see why?',
      answer: [
        {
          type: 'bullets',
          items: [
            'Orders page → Error column (often includes a reason code).',
            'System Events page → category=risk with the reason and scope key.',
            'If MANUAL mode: the order sits in the Waiting Queue until you execute it.',
          ],
        },
      ],
    },
  ],
}

export const riskSettingsHelp: HelpContext = {
  id: 'settings-risk',
  title: 'Risk settings help',
  overview: [
    'Risk Policy is your central risk configuration. When enabled, SigmaTrader blocks or clamps risky orders before they reach the broker/paper engine.',
    'Enforcement happens at dispatch/execute time (manual queue execution, TradingView AUTO, deployments, bulk execute).',
  ],
  sections: [
    {
      id: 'risk-enforcement',
      title: 'How enforcement works',
      qas: [
        {
          id: 'risk-when-enforced',
          question: 'When are risk checks applied?',
          answer: [
            {
              type: 'p',
              text: 'At order dispatch/execute time in the backend (the single enforcement choke-point). This makes enforcement consistent across all order sources.',
            },
          ],
        },
        {
          id: 'risk-selective-enforcement',
          question: 'What is selective enforcement (group toggles)?',
          answer: [
            {
              type: 'p',
              text: 'Risk Policy has a global master switch (Enable enforcement) and per-group switches. A group is enforced only when the global switch is ON and that group switch is ON.',
            },
            {
              type: 'bullets',
              items: [
                'Example: enable Stop rules & managed exits, but disable Trade frequency to avoid cooldown/limits while still keeping app-managed exits.',
                'Example: disable Overrides to ignore source/product overrides and use global settings only.',
              ],
            },
            {
              type: 'callout',
              tone: 'info',
              text: 'Defaults preserve current behavior: all groups start enabled. Turning a group OFF means SigmaTrader will not block/clamp orders due to that group.',
            },
          ],
        },
        {
          id: 'risk-blocked-behavior',
          question: 'What happens when an order is blocked?',
          answer: [
            {
              type: 'bullets',
              items: [
                'The order is not submitted to the broker/paper engine.',
                'Order status becomes REJECTED_RISK and an error message is stored.',
                'A System Event is recorded with the reason and scope key.',
              ],
            },
          ],
        },
        {
          id: 'risk-clamped-behavior',
          question: 'What does “clamped” mean?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader may reduce quantity to fit caps instead of fully rejecting. The order error message notes the clamp.',
            },
          ],
        },
      ],
    },
    {
      id: 'risk-managed-exits',
      title: 'Stops & managed exits (SigmaTrader-managed)',
      qas: [
        {
          id: 'risk-stops-app-managed',
          question: 'Are stop-loss and trailing stops enforced?',
          answer: [
            {
              type: 'p',
              text: 'Yes. When Risk Policy enforcement is enabled, SigmaTrader creates and monitors a managed exit profile for executed entries (after the entry is confirmed executed via broker/paper sync) and triggers an exit order when a stop is breached.',
            },
            {
              type: 'callout',
              tone: 'warning',
              text: 'SigmaTrader does not place broker-side SL/TP/trailing orders. It monitors and submits an exit order when triggered. This can be affected by app uptime, price gaps, and broker execution.',
            },
          ],
        },
        {
          id: 'risk-where-managed-exits',
          question: 'Where can I see monitored positions and exit orders?',
          answer: [
            {
              type: 'bullets',
              items: [
                'Queue → Managed exits tab shows positions under monitoring and their status.',
                'Exit orders are created automatically and do not appear in the manual waiting queue.',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'risk-trade-frequency-loss-controls',
      title: 'Trade frequency & loss controls',
      qas: [
        {
          id: 'risk-scope-key',
          question: 'What is the scope for trade frequency and loss controls?',
          answer: [
            {
              type: 'p',
              text: 'These controls are scoped per (st_user_id, strategy_ref, symbol, product). Strategy_ref is derived from deployment/strategy ids when available; otherwise it falls back to TradingView strategy_name or “manual”.',
            },
          ],
        },
        {
          id: 'risk-entry-only',
          question: 'What counts as a “trade” for max trades/day?',
          answer: [
            {
              type: 'p',
              text: 'Entry-only: SigmaTrader increments trades_today only when an execution opens or increases net exposure for the scope key.',
            },
            {
              type: 'callout',
              tone: 'info',
              text: 'Protective exits and exposure reductions are never blocked by these controls.',
            },
          ],
        },
        {
          id: 'risk-bars-meaning',
          question: 'How does SigmaTrader interpret “bars” between trades?',
          answer: [
            {
              type: 'p',
              text: 'Bars are derived from time and the effective interval. If interval is missing, SigmaTrader uses a default fallback (5m) and records the interval source.',
            },
          ],
        },
      ],
    },
    {
      id: 'risk-not-enforced',
      title: 'Not enforced / planned',
      qas: [
        {
          id: 'risk-correlation-not-enforced',
          question: 'Are correlation/sector controls enforced?',
          answer: [
            {
              type: 'callout',
              tone: 'warning',
              text: 'Not enforced yet. Changing these fields does not currently block executions.',
            },
          ],
        },
        {
          id: 'risk-margin-not-enforced',
          question: 'Are margin checks enforced?',
          answer: [
            {
              type: 'callout',
              tone: 'warning',
              text: 'Not enforced yet. The broker may still reject orders for insufficient margin.',
            },
          ],
        },
        {
          id: 'risk-emergency-not-enforced',
          question: 'Are error-based emergency stops enforced?',
          answer: [
            {
              type: 'callout',
              tone: 'warning',
              text: 'Not enforced yet. The UI shows the setting, but SigmaTrader does not currently halt trading based on these toggles.',
            },
          ],
        },
      ],
    },
  ],
  gettingStarted: [
    'Enable enforcement (start with PAPER mode if you want to trial safely).',
    'Set a realistic Manual equity baseline (used as the reference for several caps).',
    'Start with conservative limits: max order value, max open positions, and max trades/day.',
    'Keep broker positions synced so exposure-based limits work reliably.',
  ],
  troubleshooting: [
    {
      id: 'risk-ts-blocked',
      question: 'An order is blocked. What do I do?',
      answer: [
        {
          type: 'bullets',
          items: [
            'Open Orders and look at the Error column (often includes a reason code).',
            'Check System Events (category=risk) for a detailed record.',
            'Adjust Risk policy values (or wait for cooldown/pause windows to expire).',
          ],
        },
      ],
    },
    {
      id: 'risk-ts-reason-codes',
      question: 'What are the common reason codes?',
      answer: [{ type: 'bullets', items: reasonCodesAsBullets() }],
    },
  ],
}

export const timeSettingsHelp: HelpContext = {
  id: 'settings-time',
  title: 'Time settings help',
  overview: [
    'This tab controls how timestamps are displayed in the UI.',
    'Risk enforcement uses backend time semantics; display timezone does not change enforcement.',
  ],
  sections: [
    {
      id: 'time-display',
      title: 'Display time',
      qas: [
        {
          id: 'time-local-vs-ist',
          question: 'Does changing display timezone change risk behavior?',
          answer: [
            {
              type: 'p',
              text: 'No. Risk enforcement uses backend rules (for example, some “per day” limits reset at midnight IST). This tab only affects how times are shown.',
            },
          ],
        },
      ],
    },
  ],
  gettingStarted: ['Choose a display timezone that matches your trading workflow.'],
  troubleshooting: [
    {
      id: 'time-ts-confusion',
      question: 'My timestamps look “shifted”.',
      answer: [
        {
          type: 'p',
          text: 'Switch between Local and IST to confirm which timezone you want for display.',
        },
      ],
    },
  ],
}

export const riskManagementGuide: HelpContext = {
  id: 'risk-guide',
  title: 'Risk Management Guide',
  overview: [
    'This guide explains how SigmaTrader risk controls work today across TradingView alerts, deployments, manual queue execution, bulk execute, and internal order flows.',
    'It documents what is enforced, where it is enforced, what happens when something is blocked, and known limitations.',
  ],
  sections: [
    {
      id: 'broker-vs-app',
      title: 'SigmaTrader vs broker enforcement',
      qas: [
        {
          id: 'broker-vs-app-what',
          question: 'What does SigmaTrader enforce vs what the broker enforces?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader enforces your Risk Policy at execution time and can block/clamp orders before submission. The broker still enforces exchange/broker rules (market hours, margin, tick size, etc.).',
            },
          ],
        },
      ],
    },
    {
      id: 'chokepoint',
      title: 'Single execution choke-point',
      qas: [
        {
          id: 'chokepoint-where',
          question: 'Where is enforcement applied?',
          answer: [
            {
              type: 'p',
              text: 'In the backend at dispatch/execute time (the central execute function). This is the single enforcement choke-point used by all flows.',
            },
          ],
        },
        {
          id: 'chokepoint-selective',
          question: 'How do global vs per-group enforcement toggles work?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader applies risk checks at the choke-point, but only for groups that are enabled. Global Enable enforcement is the master switch; each group also has its own enable toggle.',
            },
            {
              type: 'bullets',
              items: [
                'Global OFF: no groups can block/clamp orders.',
                'Global ON + group OFF: that group does not block/clamp orders.',
                'Global ON + group ON: that group can block/clamp orders when its limits are hit.',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'covered-flows',
      title: 'Which flows are covered?',
      qas: [
        {
          id: 'covered-flows-list',
          question: 'Which order sources are covered by enforcement?',
          answer: [
            {
              type: 'bullets',
              items: [
                'Manual execute from Waiting Queue',
                'Bulk execute',
                'TradingView AUTO dispatch',
                'Deployments (runtime-created orders)',
                'Any internal order execution path that uses the same execute function',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'scope-keys',
      title: 'Scope keys (trade frequency & loss controls)',
      qas: [
        {
          id: 'scope-keys-definition',
          question: 'What does SigmaTrader scope trade frequency and loss controls by?',
          answer: [
            {
              type: 'bullets',
              items: [
                'st_user_id (SigmaTrader user)',
                'strategy_ref (deployment:<id> / strategy:<id> / tv:<strategy_name> / manual)',
                'symbol (canonical EXCHANGE:SYMBOL)',
                'product (MIS/CNC)',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'equity-baseline',
      title: 'Equity baseline (manual)',
      qas: [
        {
          id: 'equity-baseline-meaning',
          question: 'What is “Manual equity” and why does it matter?',
          answer: [
            {
              type: 'p',
              text: 'Manual equity is the reference balance SigmaTrader uses for percentage-based caps and sizing. Set it to match your real account size for meaningful limits.',
            },
          ],
        },
      ],
    },
    {
      id: 'account-level-limits',
      title: 'Account-level limits',
      qas: [
        {
          id: 'account-level-what',
          question: 'What account-level limits are enforced?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader enforces limits like max open positions, max concurrent symbols, and max exposure (best-effort based on positions known to SigmaTrader).',
            },
          ],
        },
      ],
    },
    {
      id: 'per-trade-risk',
      title: 'Per-trade risk',
      qas: [
        {
          id: 'per-trade-risk-what',
          question: 'What is “risk per trade” and “stop reference”?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader uses a stop reference (ATR or fixed %) to estimate stop distance for sizing and to attach managed exits when enforcement is enabled.',
            },
          ],
        },
      ],
    },
    {
      id: 'position-sizing',
      title: 'Position sizing',
      qas: [
        {
          id: 'position-sizing-what',
          question: 'How do “capital per trade”, scale-in, and pyramiding work?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader can block scale-ins when allow_scale_in is off, and it enforces a pyramiding limit (best-effort based on current positions and recent entries).',
            },
          ],
        },
      ],
    },
    {
      id: 'stop-rules-managed-exits',
      title: 'Stop rules & managed exits',
      qas: [
        {
          id: 'stop-rules-enforced',
          question: 'Are stop rules and trailing exits enforced?',
          answer: [
            {
              type: 'p',
              text: 'Yes, via SigmaTrader-managed monitoring. After an entry is executed (confirmed via broker/paper sync), SigmaTrader creates a monitored position and can submit an exit order when triggers fire.',
            },
            {
              type: 'callout',
              tone: 'warning',
              text: 'SigmaTrader does not place broker-side SL/TP/trailing orders. Keep SigmaTrader running for monitoring.',
            },
          ],
        },
        {
          id: 'stop-rules-where',
          question: 'Where do I see monitored exits?',
          answer: [
            {
              type: 'bullets',
              items: [
                'Queue → Managed exits (monitored positions and status)',
                'Orders → shows any created exit orders and their status',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'trade-frequency',
      title: 'Trade frequency',
      qas: [
        {
          id: 'trade-frequency-what',
          question: 'What is enforced in Trade frequency?',
          answer: [
            {
              type: 'bullets',
              items: [
                'max_trades_per_symbol_per_day (entry-only)',
                'min_bars_between_trades (time-derived)',
                'cooldown_after_loss_bars (time-derived after a losing close)',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'loss-controls',
      title: 'Loss controls',
      qas: [
        {
          id: 'loss-controls-what',
          question: 'What is enforced in Loss controls?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader tracks consecutive losing closes per scope key. When pause_after_loss_streak is enabled and the streak hits max_consecutive_losses, entries are paused until EOD (IST day end).',
            },
          ],
        },
      ],
    },
    {
      id: 'interval-bars',
      title: 'Intervals & “bars”',
      qas: [
        {
          id: 'interval-bars-sources',
          question: 'How does SigmaTrader determine the interval used for “bars”?',
          answer: [
            {
              type: 'bullets',
              items: [
                'tv_payload: interval from TradingView alert payload',
                'alert_rule: timeframe stored on the alert rule (when present)',
                'persisted: remembered per scope key after the first execution',
                'default_fallback: 5m when nothing else is available (logged once per scope key)',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'day-boundary',
      title: 'Day boundary semantics',
      qas: [
        {
          id: 'day-boundary-which',
          question: 'When does “per day” reset?',
          answer: [
            {
              type: 'p',
              text: 'Trade frequency and loss controls reset at midnight IST (calendar date), not at market open.',
            },
          ],
        },
      ],
    },
    {
      id: 'blocked-behavior',
      title: 'What happens when blocked?',
      qas: [
        {
          id: 'blocked-behavior-details',
          question: 'If blocked, does the order reach the broker?',
          answer: [
            {
              type: 'p',
              text: 'No. SigmaTrader rejects the execution attempt before submission.',
            },
            {
              type: 'bullets',
              items: [
                'Order status becomes REJECTED_RISK with a reason message.',
                'HTTP/API returns a 4xx with {status:"blocked", reason_code, message}.',
                'System Events records the block with details.',
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'safety-guarantees',
      title: 'Safety guarantees',
      qas: [
        {
          id: 'safety-exits',
          question: 'Are exits/protective reductions ever blocked by trade-frequency/loss-controls?',
          answer: [
            {
              type: 'p',
              text: 'No. Exposure-reducing orders are treated as exits structurally and are not blocked by these checks (with an extra is_exit safety override).',
            },
          ],
        },
      ],
    },
    {
      id: 'reason-codes',
      title: 'Glossary: reason codes',
      qas: [
        {
          id: 'reason-codes-what',
          question: 'What reason codes might I see when something is blocked?',
          answer: [
            {
              type: 'p',
              text: 'SigmaTrader uses REJECTED_RISK for blocked executions and includes a reason code/message in the order Error field and API response.',
            },
            { type: 'bullets', items: reasonCodesAsBullets() },
          ],
        },
      ],
    },
    {
      id: 'limitations',
      title: 'Known limitations (current behavior)',
      qas: [
        {
          id: 'limitations-positions-sync',
          question: 'What can cause enforcement to behave unexpectedly?',
          answer: [
            {
              type: 'bullets',
              items: [
                'If positions/orders are not synced, exposure-based checks and entry/exit classification can be less accurate.',
                'If interval/timeframe is missing, SigmaTrader falls back to a default interval for “bars”.',
                'Managed exits rely on SigmaTrader monitoring (app-managed) and broker execution; gaps/slippage are possible.',
              ],
            },
          ],
        },
        {
          id: 'limitations-not-enforced',
          question: 'Which risk settings are visible but not enforced yet?',
          answer: [
            {
              type: 'bullets',
              items: [
                'Correlation & sector controls (not enforced yet)',
                'Margin checks (not enforced yet)',
                'Error-based emergency stops (not enforced yet)',
              ],
            },
          ],
        },
      ],
    },
  ],
  gettingStarted: [
    'Enable Risk Policy enforcement.',
    'Set Manual equity baseline and conservative account-level limits.',
    'Start with max trades/day and min bars between trades to reduce overtrading.',
    'Use Managed exits for app-managed stops; keep SigmaTrader running.',
    'Check Orders + System Events whenever something is blocked.',
  ],
  troubleshooting: [
    {
      id: 'guide-ts-rejected',
      question: 'I see REJECTED_RISK. Where is the exact reason?',
      answer: [
        {
          type: 'bullets',
          items: [
            'Orders page → Error column (includes reason code/message).',
            'System Events page → category=risk for structured details.',
          ],
        },
      ],
    },
    {
      id: 'guide-ts-reason-codes',
      question: 'Common reason codes (glossary)',
      answer: [{ type: 'bullets', items: reasonCodesAsBullets() }],
    },
  ],
}

export const SETTINGS_HELP_BY_TAB = {
  broker: brokerSettingsHelp,
  risk: riskSettingsHelp,
  webhook: tradingViewWebhookHelp,
  market: marketConfigurationHelp,
  time: timeSettingsHelp,
} as const
