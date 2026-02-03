export type RiskProduct = 'CNC' | 'MIS'
export type RiskCategory = 'LC' | 'MC' | 'SC' | 'ETF'

export type RiskProfile = {
  id: number
  name: string
  product: RiskProduct

  capital_per_trade: number
  max_positions: number
  max_exposure_pct: number

  risk_per_trade_pct: number
  hard_risk_pct: number

  stop_loss_mandatory: boolean
  stop_reference: 'ATR' | 'FIXED_PCT'
  atr_period: number
  atr_mult_initial_stop: number
  fallback_stop_pct: number
  min_stop_distance_pct: number
  max_stop_distance_pct: number

  daily_loss_pct: number
  hard_daily_loss_pct: number
  max_consecutive_losses: number

  drawdown_mode: 'SETTINGS_BY_CATEGORY'

  force_exit_time?: string | null

  entry_cutoff_time?: string | null
  force_squareoff_time?: string | null
  max_trades_per_day?: number | null
  max_trades_per_symbol_per_day?: number | null
  min_bars_between_trades?: number | null
  cooldown_after_loss_bars?: number | null
  slippage_guard_bps?: number | null
  gap_guard_pct?: number | null
  order_type_policy?: string | null
  leverage_mode?: string | null
  max_effective_leverage?: number | null
  max_margin_used_pct?: number | null

  enabled: boolean
  is_default: boolean

  created_at: string
  updated_at: string
}

export type RiskProfileCreate = Omit<RiskProfile, 'id' | 'created_at' | 'updated_at'>
export type RiskProfileUpdate = Partial<RiskProfileCreate>

export type DrawdownThreshold = {
  id: number
  user_id?: number | null
  product: RiskProduct
  category: RiskCategory
  caution_pct: number
  defense_pct: number
  hard_stop_pct: number
  created_at: string
  updated_at: string
}

export type DrawdownThresholdUpsert = Pick<
  DrawdownThreshold,
  'product' | 'category' | 'caution_pct' | 'defense_pct' | 'hard_stop_pct'
>

export type SymbolRiskCategory = {
  id: number
  user_id?: number | null
  broker_name: string
  symbol: string
  exchange: string
  risk_category: RiskCategory
  created_at: string
  updated_at: string
}

export type SymbolRiskCategoryUpsert = Pick<
  SymbolRiskCategory,
  'broker_name' | 'symbol' | 'exchange' | 'risk_category'
>

export type AlertDecisionLogRow = {
  id: number
  created_at: string
  user_id?: number | null
  alert_id?: number | null
  order_id?: number | null

  source: string
  strategy_ref?: string | null
  symbol?: string | null
  exchange?: string | null
  side?: string | null
  trigger_price?: number | null

  product_hint?: string | null
  resolved_product?: string | null
  risk_profile_id?: number | null
  risk_category?: string | null
  drawdown_pct?: number | null
  drawdown_state?: string | null

  decision: string
  reasons_json: string
  details_json: string
}

export type RiskEngineV2Enabled = {
  enabled: boolean
  source: 'db' | 'env_default' | 'db_invalid'
  updated_at?: string | null
}

async function readTextSafe(res: Response): Promise<string> {
  try {
    return await res.text()
  } catch {
    return ''
  }
}

export async function fetchRiskEngineV2Enabled(): Promise<RiskEngineV2Enabled> {
  const res = await fetch('/api/risk-engine/v2-enabled', { cache: 'no-store' })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(
      `Failed to load profile engine status (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as RiskEngineV2Enabled
}

export async function updateRiskEngineV2Enabled(enabled: boolean): Promise<RiskEngineV2Enabled> {
  const res = await fetch('/api/risk-engine/v2-enabled', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ enabled: Boolean(enabled) }),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(
      `Failed to update profile engine status (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as RiskEngineV2Enabled
}

export async function fetchRiskProfiles(): Promise<RiskProfile[]> {
  const res = await fetch('/api/risk-engine/risk-profiles')
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to load risk profiles (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as RiskProfile[]
}

export async function createRiskProfile(payload: RiskProfileCreate): Promise<RiskProfile> {
  const res = await fetch('/api/risk-engine/risk-profiles', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to create risk profile (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as RiskProfile
}

export async function updateRiskProfile(
  profileId: number,
  payload: RiskProfileUpdate,
): Promise<RiskProfile> {
  const res = await fetch(`/api/risk-engine/risk-profiles/${profileId}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to update risk profile (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as RiskProfile
}

export async function deleteRiskProfile(profileId: number): Promise<void> {
  const res = await fetch(`/api/risk-engine/risk-profiles/${profileId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to delete risk profile (${res.status})${body ? `: ${body}` : ''}`)
  }
}

export async function fetchDrawdownThresholds(): Promise<DrawdownThreshold[]> {
  const res = await fetch('/api/risk-engine/drawdown-thresholds')
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(
      `Failed to load drawdown thresholds (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as DrawdownThreshold[]
}

export async function upsertDrawdownThresholds(
  payload: DrawdownThresholdUpsert[],
): Promise<DrawdownThreshold[]> {
  const res = await fetch('/api/risk-engine/drawdown-thresholds', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(
      `Failed to save drawdown thresholds (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as DrawdownThreshold[]
}

export async function fetchSymbolCategories(brokerName = 'zerodha'): Promise<SymbolRiskCategory[]> {
  const url = new URL('/api/risk-engine/symbol-categories', window.location.origin)
  url.searchParams.set('broker_name', brokerName)
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to load symbol categories (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as SymbolRiskCategory[]
}

export async function upsertSymbolCategory(
  payload: SymbolRiskCategoryUpsert,
): Promise<SymbolRiskCategory> {
  const res = await fetch('/api/risk-engine/symbol-categories', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to save symbol category (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as SymbolRiskCategory
}

export async function deleteSymbolCategory(params: {
  broker_name?: string
  exchange?: string
  symbol: string
}): Promise<void> {
  const url = new URL('/api/risk-engine/symbol-categories', window.location.origin)
  url.searchParams.set('symbol', params.symbol)
  url.searchParams.set('broker_name', params.broker_name ?? 'zerodha')
  url.searchParams.set('exchange', params.exchange ?? 'NSE')
  const res = await fetch(url.toString(), { method: 'DELETE' })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(
      `Failed to delete symbol category (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
}

export async function bulkUpsertSymbolCategories(
  payload: SymbolRiskCategoryUpsert[],
): Promise<SymbolRiskCategory[]> {
  const res = await fetch('/api/risk-engine/symbol-categories/bulk', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(
      `Failed to bulk save symbol categories (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as SymbolRiskCategory[]
}

export async function fetchAlertDecisionLog(limit = 100): Promise<AlertDecisionLogRow[]> {
  const url = new URL('/api/risk-engine/decision-log', window.location.origin)
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to load decision log (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as AlertDecisionLogRow[]
}
