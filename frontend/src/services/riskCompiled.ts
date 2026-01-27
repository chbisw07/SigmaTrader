export type RiskProduct = 'CNC' | 'MIS'
export type RiskCategory = 'LC' | 'MC' | 'SC' | 'ETF'
export type DrawdownScenario = 'NORMAL' | 'CAUTION' | 'DEFENSE' | 'HARD_STOP'

export type CompiledRiskOverride = {
  field: string
  from_value?: unknown
  to_value?: unknown
  reason: string
  source: string
}

export type CompiledRiskProvenance = {
  source:
    | 'risk_policy'
    | 'profile'
    | 'drawdown_settings'
    | 'state_override'
    | 'computed'
    | 'default'
    | 'unknown'
  detail?: string | null
}

export type CompiledRiskPolicyEffective = {
  allow_product: boolean
  allow_short_selling: boolean
  manual_equity_inr: number
  max_daily_loss_pct: number
  max_daily_loss_abs: number | null
  max_exposure_pct: number
  max_open_positions: number
  max_concurrent_symbols: number
  max_order_value_pct: number
  max_order_value_abs_from_pct: number | null
  max_order_value_abs_override: number | null
  max_quantity_per_order: number | null
  max_risk_per_trade_pct: number
  hard_max_risk_pct: number
  stop_loss_mandatory: boolean
  capital_per_trade: number
  allow_scale_in: boolean
  pyramiding: number
  stop_reference: string
  atr_period: number
  atr_mult_initial_stop: number
  fallback_stop_pct: number
  min_stop_distance_pct: number
  max_stop_distance_pct: number
  trailing_stop_enabled: boolean
  trail_activation_atr: number
  trail_activation_pct: number
  max_trades_per_symbol_per_day: number
  min_bars_between_trades: number
  cooldown_after_loss_bars: number
  max_consecutive_losses: number
  pause_after_loss_streak: boolean
  pause_duration: string
}

export type CompiledRiskV2Effective = {
  drawdown_pct: number | null
  drawdown_state: DrawdownScenario | 'NORMAL' | null
  allow_new_entries: boolean
  throttle_multiplier: number
  profile:
    | {
        id: number
        name: string
        product: RiskProduct
        enabled: boolean
        is_default: boolean
      }
    | null
  thresholds:
    | { caution_pct: number; defense_pct: number; hard_stop_pct: number }
    | null
  capital_per_trade: number | null
  max_positions: number | null
  max_exposure_pct: number | null
  risk_per_trade_pct: number | null
  hard_risk_pct: number | null
  daily_loss_pct: number | null
  hard_daily_loss_pct: number | null
  max_consecutive_losses: number | null
  entry_cutoff_time: string | null
  force_squareoff_time: string | null
  max_trades_per_day: number | null
  max_trades_per_symbol_per_day: number | null
  min_bars_between_trades: number | null
  cooldown_after_loss_bars: number | null
  slippage_guard_bps: number | null
  gap_guard_pct: number | null
}

export type CompiledRiskResponse = {
  context: {
    product: RiskProduct
    category: RiskCategory
    scenario?: DrawdownScenario | null
    symbol?: string | null
    strategy_id?: string | null
  }
  inputs: {
    compiled_at: string
    risk_policy_source: string
    risk_policy_enabled: boolean
    risk_engine_v2_enabled: boolean
    manual_equity_inr: number
    drawdown_pct: number | null
  }
  effective: {
    allow_new_entries: boolean
    blocking_reasons: string[]
    risk_policy_by_source: Record<'TRADINGVIEW' | 'SIGMATRADER', CompiledRiskPolicyEffective>
    risk_engine_v2: CompiledRiskV2Effective
  }
  overrides: CompiledRiskOverride[]
  provenance: Record<string, CompiledRiskProvenance>
}

export async function fetchCompiledRiskPolicy(params: {
  product: RiskProduct
  category: RiskCategory
  scenario?: DrawdownScenario | null
  symbol?: string | null
  strategy_id?: string | null
}): Promise<CompiledRiskResponse> {
  const url = new URL('/api/risk/compiled', window.location.origin)
  url.searchParams.set('product', params.product)
  url.searchParams.set('category', params.category)
  if (params.scenario) url.searchParams.set('scenario', params.scenario)
  if (params.symbol?.trim()) url.searchParams.set('symbol', params.symbol.trim())
  if (params.strategy_id?.trim()) url.searchParams.set('strategy_id', params.strategy_id.trim())

  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Failed to load compiled risk policy (${res.status})`)
  }
  return (await res.json()) as CompiledRiskResponse
}

