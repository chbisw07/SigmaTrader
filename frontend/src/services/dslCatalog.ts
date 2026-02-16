import { ALERT_V3_METRICS } from './alertsV3Constants'

export type DslCatalogKind =
  | 'function'
  | 'metric'
  | 'variable'
  | 'custom_indicator'
  | 'keyword'
  | 'source'
  | 'user'

export type DslCatalogItem = {
  kind: DslCatalogKind
  expr: string
  signature: string
  details: string
  insertText?: string
}

export type UserDslCatalogItem = {
  expr: string
  signature: string
  details: string
}

const DSL_CATALOG_USER_STORAGE_KEY = 'st_dsl_catalog_user_items_v1'

export function loadUserDslCatalogItems(): UserDslCatalogItem[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(DSL_CATALOG_USER_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    const out: UserDslCatalogItem[] = []
    for (const x of parsed) {
      if (!x || typeof x !== 'object') continue
      const rec = x as any
      const expr = String(rec.expr ?? '').trim()
      const signature = String(rec.signature ?? '').trim()
      const details = String(rec.details ?? '').trim()
      if (!expr || !signature) continue
      out.push({ expr, signature, details })
    }
    return out
  } catch {
    return []
  }
}

export function saveUserDslCatalogItems(items: UserDslCatalogItem[]): void {
  if (typeof window === 'undefined') return
  try {
    const cleaned = (items ?? [])
      .map((x) => ({
        expr: String(x.expr ?? '').trim(),
        signature: String(x.signature ?? '').trim(),
        details: String(x.details ?? '').trim(),
      }))
      .filter((x) => x.expr.length > 0 && x.signature.length > 0)
    window.localStorage.setItem(DSL_CATALOG_USER_STORAGE_KEY, JSON.stringify(cleaned))
  } catch {
    // ignore
  }
}

export type BuiltinDslFunction = {
  name: string
  signature: string
  snippet: string
  details: string
}

export const DSL_KEYWORDS: Array<{ expr: string; signature: string; details: string }> = [
  { expr: 'AND', signature: 'A AND B', details: 'Logical AND.' },
  { expr: 'OR', signature: 'A OR B', details: 'Logical OR.' },
  { expr: 'NOT', signature: 'NOT A', details: 'Logical NOT.' },
  { expr: 'BETWEEN', signature: 'X BETWEEN A AND B', details: 'Range check (inclusive).' },
  {
    expr: 'CROSSES_ABOVE',
    signature: 'A CROSSES_ABOVE B',
    details: 'Event operator: previous bar below/at, current bar above.',
  },
  {
    expr: 'CROSSES_BELOW',
    signature: 'A CROSSES_BELOW B',
    details: 'Event operator: previous bar above/at, current bar below.',
  },
  {
    expr: 'MOVING_UP',
    signature: 'A MOVING_UP N',
    details: 'Event operator: percent change from previous bar to current bar > N.',
  },
  {
    expr: 'MOVING_DOWN',
    signature: 'A MOVING_DOWN N',
    details: 'Event operator: percent change from previous bar to current bar < -N.',
  },
  {
    expr: 'CROSSING_ABOVE',
    signature: 'A CROSSING_ABOVE B',
    details: 'Alias for CROSSES_ABOVE.',
  },
  {
    expr: 'CROSSING_BELOW',
    signature: 'A CROSSING_BELOW B',
    details: 'Alias for CROSSES_BELOW.',
  },
]

export const DSL_SOURCES: Array<{ expr: string; signature: string; details: string }> = [
  { expr: 'open', signature: 'open', details: 'Open price series.' },
  { expr: 'high', signature: 'high', details: 'High price series.' },
  { expr: 'low', signature: 'low', details: 'Low price series.' },
  { expr: 'close', signature: 'close', details: 'Close price series.' },
  { expr: 'volume', signature: 'volume', details: 'Volume series.' },
  { expr: 'hlc3', signature: 'hlc3', details: 'Derived price: (high + low + close) / 3.' },
]

export const BUILTIN_DSL_FUNCTIONS: BuiltinDslFunction[] = [
  {
    name: 'OPEN',
    signature: 'OPEN("1d")',
    snippet: 'OPEN("${1:1d}")',
    details: 'Open price for the specified timeframe.',
  },
  {
    name: 'HIGH',
    signature: 'HIGH("1d")',
    snippet: 'HIGH("${1:1d}")',
    details: 'High price for the specified timeframe.',
  },
  {
    name: 'LOW',
    signature: 'LOW("1d")',
    snippet: 'LOW("${1:1d}")',
    details: 'Low price for the specified timeframe.',
  },
  {
    name: 'CLOSE',
    signature: 'CLOSE("1d")',
    snippet: 'CLOSE("${1:1d}")',
    details: 'Close price for the specified timeframe.',
  },
  {
    name: 'VOLUME',
    signature: 'VOLUME("1d")',
    snippet: 'VOLUME("${1:1d}")',
    details: 'Volume for the specified timeframe.',
  },
  {
    name: 'PRICE',
    signature: 'PRICE("1d")',
    snippet: 'PRICE("${1:1d}")',
    details: 'Close price alias. Also supports PRICE(source, tf) where source is open/high/low/close.',
  },

  {
    name: 'SMA',
    signature: 'SMA(close, 14, "1d")',
    snippet: 'SMA(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Simple moving average over length bars.',
  },
  {
    name: 'EMA',
    signature: 'EMA(close, 14, "1d")',
    snippet: 'EMA(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Exponential moving average over length bars.',
  },
  {
    name: 'RSI',
    signature: 'RSI(close, 14, "1d")',
    snippet: 'RSI(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Relative Strength Index over length bars.',
  },
  {
    name: 'STDDEV',
    signature: 'STDDEV(close, 14, "1d")',
    snippet: 'STDDEV(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Rolling standard deviation over length bars.',
  },
  {
    name: 'MAX',
    signature: 'MAX(close, 14, "1d")',
    snippet: 'MAX(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Rolling maximum over length bars.',
  },
  {
    name: 'MIN',
    signature: 'MIN(close, 14, "1d")',
    snippet: 'MIN(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Rolling minimum over length bars.',
  },
  {
    name: 'AVG',
    signature: 'AVG(close, 14, "1d")',
    snippet: 'AVG(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Rolling average (same shape as SMA).',
  },
  {
    name: 'SUM',
    signature: 'SUM(close, 14, "1d")',
    snippet: 'SUM(${1:close}, ${2:14}, "${3:1d}")',
    details: 'Rolling sum over length bars.',
  },

  {
    name: 'RET',
    signature: 'RET(close, "1d")',
    snippet: 'RET(${1:close}, "${2:1d}")',
    details: 'Percent return over the latest completed bar of the given timeframe.',
  },
  {
    name: 'ROC',
    signature: 'ROC(close, 14)',
    snippet: 'ROC(${1:close}, ${2:14})',
    details: 'Percent change over N bars.',
  },
  {
    name: 'LAG',
    signature: 'LAG(close, 1)',
    snippet: 'LAG(${1:close}, ${2:1})',
    details: 'Value N bars ago.',
  },
  {
    name: 'Z_SCORE',
    signature: 'Z_SCORE(close, 20)',
    snippet: 'Z_SCORE(${1:close}, ${2:20})',
    details: 'Z-score of the latest value using a rolling window.',
  },
  {
    name: 'BOLLINGER',
    signature: 'BOLLINGER(close, 20, 2)',
    snippet: 'BOLLINGER(${1:close}, ${2:20}, ${3:2})',
    details: 'Bollinger band width proxy (implementation-defined).',
  },
  {
    name: 'ATR',
    signature: 'ATR(14, "1d")',
    snippet: 'ATR(${1:14}, "${2:1d}")',
    details: 'Average True Range for the given timeframe.',
  },
  {
    name: 'ADX',
    signature: 'ADX(14, "1d")',
    snippet: 'ADX(${1:14}, "${2:1d}")',
    details: 'Average Directional Index (trend strength) using high/low/close.',
  },
  {
    name: 'MACD',
    signature: 'MACD(close, 12, 26, 9, "1d")',
    snippet: 'MACD(${1:close}, ${2:12}, ${3:26}, ${4:9}, "${5:1d}")',
    details: 'MACD line: EMA(fast) - EMA(slow).',
  },
  {
    name: 'MACD_SIGNAL',
    signature: 'MACD_SIGNAL(close, 12, 26, 9, "1d")',
    snippet: 'MACD_SIGNAL(${1:close}, ${2:12}, ${3:26}, ${4:9}, "${5:1d}")',
    details: 'MACD signal line: EMA(MACD, signalLen).',
  },
  {
    name: 'MACD_HIST',
    signature: 'MACD_HIST(close, 12, 26, 9, "1d")',
    snippet: 'MACD_HIST(${1:close}, ${2:12}, ${3:26}, ${4:9}, "${5:1d}")',
    details: 'MACD histogram: MACD - signal.',
  },

  {
    name: 'OBV',
    signature: 'OBV(close, volume, "1d")',
    snippet: 'OBV(${1:close}, ${2:volume}, "${3:1d}")',
    details: 'On-balance volume.',
  },
  {
    name: 'VWAP',
    signature: 'VWAP(hlc3, volume, "1d")',
    snippet: 'VWAP(${1:hlc3}, ${2:volume}, "${3:1d}")',
    details: 'Volume-weighted average price.',
  },

  {
    name: 'ABS',
    signature: 'ABS(x)',
    snippet: 'ABS(${1:x})',
    details: 'Absolute value.',
  },
  {
    name: 'SQRT',
    signature: 'SQRT(x)',
    snippet: 'SQRT(${1:x})',
    details: 'Square root.',
  },
  {
    name: 'LOG',
    signature: 'LOG(x)',
    snippet: 'LOG(${1:x})',
    details: 'Natural logarithm.',
  },
  {
    name: 'EXP',
    signature: 'EXP(x)',
    snippet: 'EXP(${1:x})',
    details: 'e^x.',
  },
  {
    name: 'POW',
    signature: 'POW(x, y)',
    snippet: 'POW(${1:x}, ${2:y})',
    details: 'x raised to power y.',
  },
]

const METRIC_DETAILS: Record<(typeof ALERT_V3_METRICS)[number], string> = {
  TODAY_PNL_PCT: 'Holding metric: today’s PnL percentage (broker “day change” style).',
  PNL_PCT: 'Holding metric: total PnL percentage.',
  MAX_PNL_PCT: 'Holding metric: max PnL percentage since entry (if available).',
  DRAWDOWN_PCT: 'Holding metric: drawdown from peak PnL percentage (if available).',
  INVESTED: 'Holding metric: invested amount/value.',
  CURRENT_VALUE: 'Holding metric: current value.',
  QTY: 'Holding metric: current quantity.',
  AVG_PRICE: 'Holding metric: average price.',
}

export function buildDslCatalog({
  operands = [],
  customIndicators = [],
  userItems = [],
}: {
  operands?: string[]
  customIndicators?: Array<{ name: string; params?: string[]; description?: string | null }>
  userItems?: UserDslCatalogItem[]
}): DslCatalogItem[] {
  const items: DslCatalogItem[] = []

  for (const fn of BUILTIN_DSL_FUNCTIONS) {
    items.push({
      kind: 'function',
      expr: fn.name,
      signature: fn.signature,
      details: fn.details,
      insertText: fn.signature,
    })
  }

  for (const k of DSL_KEYWORDS) {
    items.push({
      kind: 'keyword',
      expr: k.expr,
      signature: k.signature,
      details: k.details,
      insertText: k.expr,
    })
  }

  for (const s of DSL_SOURCES) {
    items.push({
      kind: 'source',
      expr: s.expr,
      signature: s.signature,
      details: s.details,
      insertText: s.expr,
    })
  }

  for (const m of ALERT_V3_METRICS) {
    items.push({
      kind: 'metric',
      expr: m,
      signature: m,
      details: METRIC_DETAILS[m],
      insertText: m,
    })
  }

  const metricsSet = new Set((ALERT_V3_METRICS as readonly string[]).map((x) => String(x)))
  const variables = (operands ?? [])
    .map((x) => String(x || '').trim())
    .filter(Boolean)
    .filter((x) => !metricsSet.has(x))
    .sort((a, b) => a.localeCompare(b))
  for (const v of variables) {
    items.push({
      kind: 'variable',
      expr: v,
      signature: v,
      details: 'Variable (defined in this screen / run).',
      insertText: v,
    })
  }

  const customs = (customIndicators ?? [])
    .map((ci) => ({
      name: (ci.name || '').trim(),
      params: Array.isArray(ci.params) ? ci.params : [],
      description: ci.description || '',
    }))
    .filter((ci) => ci.name.length > 0)
    .sort((a, b) => a.name.localeCompare(b.name))
  for (const ci of customs) {
    const args = ci.params.length ? ci.params.join(', ') : ''
    items.push({
      kind: 'custom_indicator',
      expr: ci.name,
      signature: `${ci.name}(${args})`,
      details: ci.description || 'Custom indicator function.',
      insertText: `${ci.name}(${args})`,
    })
  }

  const users = (userItems ?? [])
    .map((x) => ({
      expr: String(x.expr || '').trim(),
      signature: String(x.signature || '').trim(),
      details: String(x.details || '').trim(),
    }))
    .filter((x) => x.expr.length > 0 && x.signature.length > 0)
    .sort((a, b) => a.expr.localeCompare(b.expr))
  for (const u of users) {
    items.push({
      kind: 'user',
      expr: u.expr,
      signature: u.signature,
      details: u.details || 'User-defined snippet.',
      insertText: u.signature,
    })
  }

  return items
}
