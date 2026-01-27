import type { RiskCategory, SymbolRiskCategory } from '../services/riskEngine'

function tsMs(v: string | null | undefined): number {
  if (!v) return 0
  const ms = Date.parse(v)
  return Number.isFinite(ms) ? ms : 0
}

export function resolveSymbolRiskCategory(
  rows: SymbolRiskCategory[],
  params: { broker_name: string; exchange: string; symbol: string },
): RiskCategory | null {
  const symbol = (params.symbol || '').trim().toUpperCase()
  if (!symbol) return null
  const exchange = (params.exchange || 'NSE').trim().toUpperCase() || 'NSE'
  const broker = (params.broker_name || 'zerodha').trim().toLowerCase() || 'zerodha'

  let best: SymbolRiskCategory | null = null
  let bestTs = 0
  for (const r of rows) {
    if ((r.symbol || '').trim().toUpperCase() !== symbol) continue
    const rBroker = (r.broker_name || '').trim().toLowerCase()
    const rEx = (r.exchange || '').trim().toUpperCase() || 'NSE'
    if (rBroker !== broker && rBroker !== '*') continue
    if (rEx !== exchange && rEx !== '*') continue

    const t = tsMs(r.updated_at)
    if (best == null || t > bestTs) {
      best = r
      bestTs = t
    }
  }
  return best?.risk_category ?? null
}

