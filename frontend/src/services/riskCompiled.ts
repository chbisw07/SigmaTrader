export type RiskProduct = 'CNC' | 'MIS'
export type RiskCategory = 'LC' | 'MC' | 'SC' | 'ETF'
export type RiskSourceBucket = 'TRADINGVIEW' | 'SIGMATRADER' | 'MANUAL'
export type DrawdownScenario = 'NORMAL' | 'CAUTION' | 'DEFENSE' | 'HARD_STOP'

export type CompiledRiskOverride = {
  field: string
  from_value?: unknown
  to_value?: unknown
  reason: string
  source: string
}

export type CompiledRiskProvenance = {
  source: 'global' | 'profile' | 'source_override' | 'computed' | 'default' | 'unknown'
  detail?: string | null
}

export type CompiledRiskProfileRef = {
  id: number
  name: string
  product: RiskProduct
  enabled: boolean
  is_default: boolean
}

export type CompiledDrawdownThresholds = {
  caution_pct: number
  defense_pct: number
  hard_stop_pct: number
}

export type CompiledRiskEffective = {
  allow_new_entries: boolean
  blocking_reasons: string[]
  drawdown_state: DrawdownScenario | null
  throttle_multiplier: number

  profile: CompiledRiskProfileRef | null
  thresholds: CompiledDrawdownThresholds | null

  allow_product: boolean
  allow_short_selling: boolean
  max_order_value_pct: number | null
  max_order_value_abs: number | null
  max_quantity_per_order: number | null
  order_type_policy: string | null
  slippage_guard_bps: number | null
  gap_guard_pct: number | null

  capital_per_trade: number | null
  max_positions: number | null
  max_exposure_pct: number | null

  daily_loss_pct: number | null
  hard_daily_loss_pct: number | null
  max_consecutive_losses: number | null

  risk_per_trade_pct: number | null
  hard_risk_pct: number | null

  stop_loss_mandatory: boolean | null
  stop_reference: string | null
  atr_period: number | null
  atr_mult_initial_stop: number | null
  fallback_stop_pct: number | null
  min_stop_distance_pct: number | null
  max_stop_distance_pct: number | null

  entry_cutoff_time: string | null
  force_squareoff_time: string | null
  max_trades_per_day: number | null
  max_trades_per_symbol_per_day: number | null
  min_bars_between_trades: number | null
  cooldown_after_loss_bars: number | null
}

export type CompiledRiskResponse = {
  context: {
    product: RiskProduct
    category: RiskCategory
    source_bucket: RiskSourceBucket
    order_type: string | null
    scenario: DrawdownScenario | null
    symbol: string | null
    strategy_id: string | null
  }
  inputs: {
    compiled_at: string
    risk_enabled: boolean
    manual_override_enabled: boolean
    baseline_equity_inr: number
    drawdown_pct: number | null
  }
  effective: CompiledRiskEffective
  overrides: CompiledRiskOverride[]
  provenance: Record<string, CompiledRiskProvenance>
}

export async function fetchCompiledRiskPolicy(params: {
  product: RiskProduct
  category: RiskCategory
  source_bucket: RiskSourceBucket
  order_type?: string | null
  scenario?: DrawdownScenario | null
  symbol?: string | null
  strategy_id?: string | null
}): Promise<CompiledRiskResponse> {
  const url = new URL('/api/risk/compiled', window.location.origin)
  url.searchParams.set('product', params.product)
  url.searchParams.set('category', params.category)
  url.searchParams.set('source_bucket', params.source_bucket)
  if (params.order_type?.trim()) url.searchParams.set('order_type', params.order_type.trim())
  if (params.scenario) url.searchParams.set('scenario', params.scenario)
  if (params.symbol?.trim()) url.searchParams.set('symbol', params.symbol.trim())
  if (params.strategy_id?.trim()) url.searchParams.set('strategy_id', params.strategy_id.trim())

  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Failed to load effective risk summary (${res.status})`)
  }
  return (await res.json()) as CompiledRiskResponse
}

