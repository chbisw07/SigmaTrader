export type IndicatorType =
  | 'PRICE'
  | 'RSI'
  | 'MA'
  | 'MA_CROSS'
  | 'VOLATILITY'
  | 'ATR'
  | 'PERF_PCT'
  | 'VOLUME_RATIO'
  | 'VWAP'

export type OperatorType =
  | 'GT'
  | 'LT'
  | 'CROSS_ABOVE'
  | 'CROSS_BELOW'
  | 'BETWEEN'
  | 'OUTSIDE'
  | 'MOVE_UP_PCT'
  | 'MOVE_DOWN_PCT'

export type TriggerMode = 'ONCE' | 'ONCE_PER_BAR' | 'EVERY_TIME'

export type ActionType = 'ALERT_ONLY' | 'SELL_PERCENT' | 'BUY_QUANTITY'

export type LogicType = 'AND' | 'OR'

export type UniverseType = 'HOLDINGS'

export type IndicatorCondition = {
  indicator: IndicatorType
  operator: OperatorType
  threshold_1: number
  threshold_2?: number | null
  params?: Record<string, unknown>
}

export type IndicatorRule = {
  id: number
  strategy_id?: number | null
  name?: string | null
  symbol?: string | null
  universe?: UniverseType | null
  exchange?: string | null
  timeframe: string
  logic: LogicType
  conditions: IndicatorCondition[]
  trigger_mode: TriggerMode
  action_type: ActionType
  action_params: Record<string, unknown>
  expires_at?: string | null
  enabled: boolean
  last_triggered_at?: string | null
  created_at: string
  updated_at: string
}

export type IndicatorRuleCreate = {
  strategy_id?: number | null
  name?: string | null
  symbol?: string | null
  universe?: UniverseType | null
  exchange?: string | null
  timeframe: string
  logic: LogicType
  conditions: IndicatorCondition[]
  trigger_mode: TriggerMode
  action_type: ActionType
  action_params?: Record<string, unknown>
  expires_at?: string | null
  enabled?: boolean
}

export type IndicatorRuleUpdate = Partial<
  Omit<IndicatorRuleCreate, 'symbol' | 'universe'>
> & {
  symbol?: string | null
  universe?: UniverseType | null
}

export type IndicatorPreview = {
  value: number | null
  prev_value: number | null
  bar_time: string | null
}

export async function listIndicatorRules(
  symbol?: string,
): Promise<IndicatorRule[]> {
  const url = new URL('/api/indicator-alerts/', window.location.origin)
  if (symbol) {
    url.searchParams.set('symbol', symbol)
  }

  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load indicator rules (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as IndicatorRule[]
}

export async function createIndicatorRule(
  payload: IndicatorRuleCreate,
): Promise<IndicatorRule> {
  const res = await fetch('/api/indicator-alerts/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to create indicator rule (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as IndicatorRule
}

export async function updateIndicatorRule(
  id: number,
  payload: IndicatorRuleUpdate,
): Promise<IndicatorRule> {
  const res = await fetch(`/api/indicator-alerts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to update indicator rule (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as IndicatorRule
}

export async function deleteIndicatorRule(id: number): Promise<void> {
  const res = await fetch(`/api/indicator-alerts/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to delete indicator rule (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
}

export async function fetchIndicatorPreview(params: {
  symbol: string
  exchange?: string
  timeframe: string
  indicator: IndicatorType
  period?: number
  window?: number
}): Promise<IndicatorPreview> {
  const url = new URL('/api/indicator-alerts/preview', window.location.origin)
  url.searchParams.set('symbol', params.symbol)
  url.searchParams.set('timeframe', params.timeframe)
  url.searchParams.set('indicator', params.indicator)
  if (params.exchange) {
    url.searchParams.set('exchange', params.exchange)
  }
  if (params.period != null) {
    url.searchParams.set('period', String(params.period))
  }
  if (params.window != null) {
    url.searchParams.set('window', String(params.window))
  }

  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load indicator preview (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as IndicatorPreview
}
