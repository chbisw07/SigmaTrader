export const ALERT_V3_TIMEFRAMES = [
  '1m',
  '5m',
  '15m',
  '1h',
  '1d',
  '1w',
  '2w',
  '1mo',
  '3mo',
  '6mo',
  '1y',
  '2y',
] as const

export const ALERT_V3_METRICS = [
  'TODAY_PNL_PCT',
  'PNL_PCT',
  'MAX_PNL_PCT',
  'DRAWDOWN_PCT',
  'INVESTED',
  'CURRENT_VALUE',
  'QTY',
  'AVG_PRICE',
] as const

export const ALERT_V3_SOURCES = ['open', 'high', 'low', 'close', 'volume'] as const

