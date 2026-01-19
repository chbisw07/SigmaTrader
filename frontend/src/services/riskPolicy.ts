export type OrderSourceBucket = 'TRADINGVIEW' | 'SIGMATRADER'
export type ProductType = 'MIS' | 'CNC'

export type ProductOverrides = {
  allow?: boolean | null
  max_order_value_abs?: number | null
  max_quantity_per_order?: number | null
  capital_per_trade?: number | null
  max_risk_per_trade_pct?: number | null
  hard_max_risk_pct?: number | null
}

export type RiskPolicy = {
  version: number
  enabled: boolean
  equity: {
    equity_mode: 'MANUAL'
    manual_equity_inr: number
  }
  account_risk: {
    max_daily_loss_pct: number
    max_daily_loss_abs: number | null
    max_open_positions: number
    max_concurrent_symbols: number
    max_exposure_pct: number
  }
  trade_risk: {
    max_risk_per_trade_pct: number
    hard_max_risk_pct: number
    stop_loss_mandatory: boolean
    stop_reference: 'ATR' | 'FIXED_PCT'
  }
  position_sizing: {
    sizing_mode: 'FIXED_CAPITAL'
    capital_per_trade: number
    allow_scale_in: boolean
    pyramiding: number
  }
  stop_rules: {
    atr_period: number
    initial_stop_atr: number
    fallback_stop_pct: number
    min_stop_distance_pct: number
    max_stop_distance_pct: number
    trailing_stop_enabled: boolean
    trail_activation_atr: number
  }
  trade_frequency: {
    max_trades_per_symbol_per_day: number
    min_bars_between_trades: number
    cooldown_after_loss_bars: number
  }
  loss_controls: {
    max_consecutive_losses: number
    pause_after_loss_streak: boolean
    pause_duration: string
  }
  correlation_rules: {
    max_same_sector_positions: number
    sector_correlation_limit: number
  }
  execution_safety: {
    allow_mis: boolean
    allow_cnc: boolean
    allow_short_selling: boolean
    max_order_value_pct: number
    reject_if_margin_exceeded: boolean
  }
  emergency_controls: {
    panic_stop: boolean
    stop_all_trading_on_error: boolean
    stop_on_unexpected_qty: boolean
  }
  overrides: Record<OrderSourceBucket, Record<ProductType, ProductOverrides>>
}

export type RiskPolicyRead = {
  policy: RiskPolicy
  source: 'db' | 'default'
}

export async function fetchRiskPolicy(): Promise<RiskPolicyRead> {
  const res = await fetch('/api/risk-policy')
  if (!res.ok) throw new Error(`Failed to load risk policy (${res.status})`)
  return (await res.json()) as RiskPolicyRead
}

export async function fetchDefaultRiskPolicy(): Promise<RiskPolicy> {
  const res = await fetch('/api/risk-policy/defaults')
  if (!res.ok) throw new Error(`Failed to load default risk policy (${res.status})`)
  return (await res.json()) as RiskPolicy
}

export async function updateRiskPolicy(policy: RiskPolicy): Promise<RiskPolicy> {
  const res = await fetch('/api/risk-policy', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to update risk policy (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as RiskPolicy
}

export async function resetRiskPolicy(): Promise<RiskPolicy> {
  const res = await fetch('/api/risk-policy/reset', { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to reset risk policy (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as RiskPolicy
}

