export type RebalanceBroker = 'zerodha' | 'angelone' | 'both'
export type RebalanceMode = 'MANUAL' | 'AUTO'
export type RebalanceTargetKind = 'GROUP' | 'HOLDINGS'

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
}

export async function previewRebalance(payload: {
  target_kind: RebalanceTargetKind
  group_id?: number | null
  broker_name: RebalanceBroker
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
