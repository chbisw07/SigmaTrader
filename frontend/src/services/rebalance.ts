export type RebalanceBroker = 'zerodha' | 'angelone' | 'both'
export type RebalanceMode = 'MANUAL' | 'AUTO'
export type RebalanceTargetKind = 'GROUP' | 'HOLDINGS'
export type RebalanceMethod = 'TARGET_WEIGHT' | 'SIGNAL_ROTATION' | 'RISK_PARITY'
export type RebalanceRotationWeighting = 'EQUAL' | 'SCORE' | 'RANK'

export type RebalanceRotationConfig = {
  signal_strategy_version_id: number
  signal_output: string
  signal_params?: Record<string, unknown>
  universe_group_id?: number | null
  screener_run_id?: number | null
  top_n: number
  weighting: RebalanceRotationWeighting
  sell_not_in_top_n: boolean
  min_price?: number | null
  min_avg_volume_20d?: number | null
  symbol_whitelist?: string[]
  symbol_blacklist?: string[]
  require_positive_score: boolean
}

export type RebalanceRiskWindow = '6M' | '1Y'

export type RebalanceRiskConfig = {
  window: RebalanceRiskWindow
  timeframe: '1d'
  min_observations: number
  min_weight: number
  max_weight: number
  max_iter: number
  tol: number
}

export type RebalanceTrade = {
  symbol: string
  exchange?: string | null
  side: 'BUY' | 'SELL'
  qty: number
  estimated_price: number
  estimated_notional: number
  target_weight: number
  live_weight: number
  drift: number
  current_value: number
  desired_value: number
  delta_value: number
  scale: number
  reason?: Record<string, unknown>
}

export type RebalancePreviewSummary = {
  portfolio_value: number
  budget: number
  scale: number
  total_buy_value: number
  total_sell_value: number
  turnover_pct: number
  budget_used: number
  budget_used_pct: number
  max_abs_drift_before: number
  max_abs_drift_after: number
  trades_count: number
}

export type RebalancePreviewResult = {
  target_kind: RebalanceTargetKind
  group_id?: number | null
  broker_name: 'zerodha' | 'angelone'
  trades: RebalanceTrade[]
  summary: RebalancePreviewSummary
  warnings: string[]
  derived_targets?: Array<Record<string, unknown>> | null
}

export async function previewRebalance(payload: {
  target_kind: RebalanceTargetKind
  group_id?: number | null
  broker_name: RebalanceBroker
  rebalance_method?: RebalanceMethod | null
  rotation?: RebalanceRotationConfig | null
  risk?: RebalanceRiskConfig | null
  budget_pct?: number | null
  budget_amount?: number | null
  drift_band_abs_pct?: number | null
  drift_band_rel_pct?: number | null
  max_trades?: number | null
  min_trade_value?: number | null
}): Promise<RebalancePreviewResult[]> {
  const res = await fetch('/api/rebalance/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to preview rebalance (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  const data = (await res.json()) as { results: RebalancePreviewResult[] }
  return data.results ?? []
}

export type RebalanceRunOrder = {
  id: number
  run_id: number
  order_id?: number | null
  symbol: string
  exchange?: string | null
  side: string
  qty: number
  estimated_price?: number | null
  estimated_notional?: number | null
  status: string
  created_at: string
}

export type RebalanceRun = {
  id: number
  owner_id?: number | null
  group_id: number
  broker_name: string
  status: string
  mode: string
  idempotency_key?: string | null
  summary_json?: string | null
  error_message?: string | null
  created_at: string
  executed_at?: string | null
  orders: RebalanceRunOrder[]
}

export async function executeRebalance(payload: {
  target_kind: RebalanceTargetKind
  group_id?: number | null
  broker_name: RebalanceBroker
  rebalance_method?: RebalanceMethod | null
  rotation?: RebalanceRotationConfig | null
  risk?: RebalanceRiskConfig | null
  budget_pct?: number | null
  budget_amount?: number | null
  drift_band_abs_pct?: number | null
  drift_band_rel_pct?: number | null
  max_trades?: number | null
  min_trade_value?: number | null
  mode: RebalanceMode
  execution_target: 'LIVE' | 'PAPER'
  order_type: 'MARKET' | 'LIMIT'
  product: 'CNC' | 'MIS'
  idempotency_key?: string | null
}): Promise<Array<{ run: RebalanceRun | null; created_order_ids: number[] }>> {
  const res = await fetch('/api/rebalance/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to execute rebalance (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  const data = (await res.json()) as {
    results: Array<{ run?: RebalanceRun | null; created_order_ids: number[] }>
  }
  return (data.results ?? []).map((r) => ({
    run: (r.run ?? null) as RebalanceRun | null,
    created_order_ids: r.created_order_ids ?? [],
  }))
}

export async function listRebalanceRuns(params: {
  group_id?: number
  broker_name?: 'zerodha' | 'angelone' | null
}): Promise<RebalanceRun[]> {
  const search = new URLSearchParams()
  if (params.group_id != null) search.set('group_id', String(params.group_id))
  if (params.broker_name) search.set('broker_name', params.broker_name)
  const url = `/api/rebalance/runs${search.toString() ? `?${search}` : ''}`
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load rebalance history (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as RebalanceRun[]
}

export async function getRebalanceRun(runId: number): Promise<RebalanceRun> {
  const res = await fetch(`/api/rebalance/runs/${runId}`)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load rebalance run (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as RebalanceRun
}

export type RebalanceScheduleFrequency =
  | 'WEEKLY'
  | 'MONTHLY'
  | 'QUARTERLY'
  | 'CUSTOM_DAYS'

export type RebalanceScheduleRoll = 'NEXT' | 'PREV' | 'NONE'

export type RebalanceScheduleConfig = {
  frequency: RebalanceScheduleFrequency
  time_local: string
  timezone: string
  weekday?: number | null
  day_of_month?: number | 'LAST' | null
  interval_days?: number | null
  roll_to_trading_day: RebalanceScheduleRoll
}

export type RebalanceSchedule = {
  group_id: number
  enabled: boolean
  config: RebalanceScheduleConfig
  next_run_at?: string | null
  last_run_at?: string | null
  updated_at?: string | null
}

export async function fetchRebalanceSchedule(groupId: number): Promise<RebalanceSchedule> {
  const res = await fetch(`/api/rebalance/schedule?group_id=${groupId}`)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load rebalance schedule (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as RebalanceSchedule
}

export async function updateRebalanceSchedule(
  groupId: number,
  payload: {
    enabled?: boolean
    config?: RebalanceScheduleConfig
  },
): Promise<RebalanceSchedule> {
  const res = await fetch(`/api/rebalance/schedule?group_id=${groupId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to update rebalance schedule (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as RebalanceSchedule
}
