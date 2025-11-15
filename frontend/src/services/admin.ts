export type Strategy = {
  id: number
  name: string
  description?: string | null
  execution_mode: 'AUTO' | 'MANUAL'
  enabled: boolean
}

export type RiskSettings = {
  id: number
  scope: 'GLOBAL' | 'STRATEGY'
  strategy_id?: number | null
  max_order_value?: number | null
  max_quantity_per_order?: number | null
  max_daily_loss?: number | null
  allow_short_selling: boolean
  max_open_positions?: number | null
  clamp_mode: 'CLAMP' | 'REJECT'
  symbol_whitelist?: string | null
  symbol_blacklist?: string | null
}

export async function fetchStrategies(): Promise<Strategy[]> {
  const res = await fetch('/api/strategies/')
  if (!res.ok) {
    throw new Error(`Failed to load strategies (${res.status})`)
  }
  return (await res.json()) as Strategy[]
}

export async function fetchRiskSettings(): Promise<RiskSettings[]> {
  const res = await fetch('/api/risk-settings/')
  if (!res.ok) {
    throw new Error(`Failed to load risk settings (${res.status})`)
  }
  return (await res.json()) as RiskSettings[]
}

