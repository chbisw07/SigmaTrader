export type RiskProduct = 'CNC' | 'MIS'
export type RiskSourceBucket = 'TRADINGVIEW' | 'SIGMATRADER'

export type UnifiedRiskGlobal = {
  enabled: boolean
  manual_override_enabled: boolean
  baseline_equity_inr: number
  no_trade_rules: string
  updated_at?: string | null
}

export type UnifiedRiskGlobalUpdate = Omit<UnifiedRiskGlobal, 'updated_at'>

export type RiskSourceOverride = {
  source_bucket: RiskSourceBucket
  product: RiskProduct

  allow_product?: boolean | null

  allow_short_selling?: boolean | null
  max_order_value_pct?: number | null
  max_order_value_abs?: number | null
  max_quantity_per_order?: number | null

  capital_per_trade?: number | null
  max_positions?: number | null
  max_exposure_pct?: number | null

  risk_per_trade_pct?: number | null
  hard_risk_pct?: number | null
  stop_loss_mandatory?: boolean | null
  stop_reference?: 'ATR' | 'FIXED_PCT' | null
  atr_period?: number | null
  atr_mult_initial_stop?: number | null
  fallback_stop_pct?: number | null
  min_stop_distance_pct?: number | null
  max_stop_distance_pct?: number | null

  daily_loss_pct?: number | null
  hard_daily_loss_pct?: number | null
  max_consecutive_losses?: number | null

  entry_cutoff_time?: string | null
  force_squareoff_time?: string | null
  max_trades_per_day?: number | null
  max_trades_per_symbol_per_day?: number | null
  min_bars_between_trades?: number | null
  cooldown_after_loss_bars?: number | null

  slippage_guard_bps?: number | null
  gap_guard_pct?: number | null
  order_type_policy?: string | null

  updated_at?: string | null
}

async function readTextSafe(res: Response): Promise<string> {
  try {
    return await res.text()
  } catch {
    return ''
  }
}

export async function fetchUnifiedRiskGlobal(): Promise<UnifiedRiskGlobal> {
  const res = await fetch('/api/risk/global', { cache: 'no-store' })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to load risk settings (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as UnifiedRiskGlobal
}

export async function updateUnifiedRiskGlobal(
  payload: UnifiedRiskGlobalUpdate,
): Promise<UnifiedRiskGlobal> {
  const res = await fetch('/api/risk/global', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to save risk settings (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as UnifiedRiskGlobal
}

export async function fetchRiskSourceOverrides(): Promise<RiskSourceOverride[]> {
  const res = await fetch('/api/risk/source-overrides', { cache: 'no-store' })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to load risk source overrides (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as RiskSourceOverride[]
}

export async function upsertRiskSourceOverride(
  payload: Omit<RiskSourceOverride, 'updated_at'>,
): Promise<RiskSourceOverride> {
  const res = await fetch('/api/risk/source-overrides', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to save risk source override (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as RiskSourceOverride
}

export async function deleteRiskSourceOverride(params: {
  source_bucket: RiskSourceBucket
  product: RiskProduct
}): Promise<{ deleted: boolean }> {
  const res = await fetch(
    `/api/risk/source-overrides/${encodeURIComponent(params.source_bucket)}/${encodeURIComponent(params.product)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to delete risk source override (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as { deleted: boolean }
}
