import { describe, expect, it } from 'vitest'

import { computeHoldingsWeights, normalizeTargetWeights } from './groupWeights'

describe('groupWeights', () => {
  it('normalizes target weights: all unspecified -> equal weights', () => {
    const w = normalizeTargetWeights([
      { exchange: 'NSE', symbol: 'TCS', target_weight: null },
      { exchange: 'NSE', symbol: 'INFY', target_weight: null },
    ])
    expect(w['NSE:TCS']).toBeCloseTo(0.5)
    expect(w['NSE:INFY']).toBeCloseTo(0.5)
  })

  it('normalizes target weights: specified sum < 1 distributes leftover', () => {
    const w = normalizeTargetWeights([
      { exchange: 'NSE', symbol: 'TCS', target_weight: 0.2 },
      { exchange: 'NSE', symbol: 'INFY', target_weight: null },
      { exchange: 'NSE', symbol: 'HDFCBANK', target_weight: null },
    ])
    expect(w['NSE:TCS']).toBeCloseTo(0.2)
    expect(w['NSE:INFY']).toBeCloseTo(0.4)
    expect(w['NSE:HDFCBANK']).toBeCloseTo(0.4)
    const sum = Object.values(w).reduce((a, b) => a + b, 0)
    expect(sum).toBeCloseTo(1.0)
  })

  it('normalizes target weights: specified sum >= 1 normalizes down', () => {
    const w = normalizeTargetWeights([
      { exchange: 'NSE', symbol: 'TCS', target_weight: 0.8 },
      { exchange: 'NSE', symbol: 'INFY', target_weight: 0.8 },
      { exchange: 'NSE', symbol: 'HDFCBANK', target_weight: null },
    ])
    expect(w['NSE:TCS']).toBeCloseTo(0.5)
    expect(w['NSE:INFY']).toBeCloseTo(0.5)
    expect(w['NSE:HDFCBANK']).toBeCloseTo(0.0)
    const sum = Object.values(w).reduce((a, b) => a + b, 0)
    expect(sum).toBeCloseTo(1.0)
  })

  it('computes holdings weights using value (qty*price), falls back to qty', () => {
    const holdingsByKey = {
      'NSE:TCS': { qty: 10, avgPrice: 100, lastPrice: 200 },
      'NSE:INFY': { qty: 30, avgPrice: 100, lastPrice: 100 },
    }
    const resolve = (exchange: string | null | undefined, symbol: string | null | undefined) => {
      const k = `${(exchange || 'NSE').toUpperCase()}:${(symbol || '').toUpperCase()}`
      return (holdingsByKey as any)[k] ?? null
    }
    const w = computeHoldingsWeights(
      [
        { exchange: 'NSE', symbol: 'TCS' },
        { exchange: 'NSE', symbol: 'INFY' },
      ],
      resolve,
    )
    // Values: TCS=10*200=2000, INFY=30*100=3000 => weights 0.4 / 0.6
    expect(w['NSE:TCS']).toBeCloseTo(0.4)
    expect(w['NSE:INFY']).toBeCloseTo(0.6)
  })
})

