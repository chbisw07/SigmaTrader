import { describe, expect, it } from 'vitest'

import {
  clearUnlocked,
  computeWeightModeAllocation,
  equalizeUnlocked,
  normalizeUnlocked,
  sumLockedWeightPct,
  sumWeightPct,
} from './engine'
import type { AllocationRowDraft } from './types'

function rows(weights: Array<{ id: string; w: number; locked?: boolean }>): AllocationRowDraft[] {
  return weights.map((x) => ({
    id: x.id,
    symbol: x.id,
    exchange: 'NSE',
    weightPct: x.w,
    locked: Boolean(x.locked),
  }))
}

describe('allocation engine (weight mode)', () => {
  it('equalizeUnlocked splits remaining across unlocked and sums to 100', () => {
    const next = equalizeUnlocked(rows([{ id: 'A', w: 0 }, { id: 'B', w: 0 }, { id: 'C', w: 0 }]))
    expect(sumWeightPct(next)).toBeCloseTo(100, 6)
    expect(next.map((r) => r.weightPct).reduce((a, b) => a + b, 0)).toBeCloseTo(100, 6)
  })

  it('equalizeUnlocked respects locked weights', () => {
    const next = equalizeUnlocked(
      rows([
        { id: 'A', w: 60, locked: true },
        { id: 'B', w: 0 },
        { id: 'C', w: 0 },
      ]),
    )
    expect(sumLockedWeightPct(next)).toBeCloseTo(60, 6)
    expect(sumWeightPct(next)).toBeCloseTo(100, 6)
    expect(next.find((r) => r.id === 'B')?.weightPct).toBeCloseTo(20, 6)
    expect(next.find((r) => r.id === 'C')?.weightPct).toBeCloseTo(20, 6)
  })

  it('normalizeUnlocked scales unlocked weights to fill remaining', () => {
    const next = normalizeUnlocked(
      rows([
        { id: 'L', w: 20, locked: true },
        { id: 'A', w: 10 },
        { id: 'B', w: 30 },
      ]),
    )
    expect(sumWeightPct(next)).toBeCloseTo(100, 6)
    expect(next.find((r) => r.id === 'A')?.weightPct).toBeCloseTo(20, 6)
    expect(next.find((r) => r.id === 'B')?.weightPct).toBeCloseTo(60, 6)
  })

  it('normalizeUnlocked falls back to equalize when unlocked sum is 0', () => {
    const next = normalizeUnlocked(
      rows([
        { id: 'L', w: 25, locked: true },
        { id: 'A', w: 0 },
        { id: 'B', w: 0 },
        { id: 'C', w: 0 },
      ]),
    )
    expect(sumWeightPct(next)).toBeCloseTo(100, 6)
    expect(next.filter((r) => !r.locked).map((r) => r.weightPct).reduce((a, b) => a + b, 0)).toBeCloseTo(
      75,
      6,
    )
  })

  it('clearUnlocked zeroes only unlocked rows', () => {
    const next = clearUnlocked(
      rows([
        { id: 'L', w: 40, locked: true },
        { id: 'A', w: 30 },
        { id: 'B', w: 30 },
      ]),
    )
    expect(next.find((r) => r.id === 'L')?.weightPct).toBe(40)
    expect(next.find((r) => r.id === 'A')?.weightPct).toBe(0)
    expect(next.find((r) => r.id === 'B')?.weightPct).toBe(0)
  })

  it('computeWeightModeAllocation computes planned qty and remaining funds', () => {
    const res = computeWeightModeAllocation({
      funds: 1000,
      rows: rows([
        { id: 'A', w: 50 },
        { id: 'B', w: 50 },
      ]),
      pricesByRowId: { A: 100, B: 200 },
      requireWeightsSumTo100: true,
    })
    expect(res.issues.find((i) => i.level === 'error')).toBeFalsy()
    expect(res.rows.find((r) => r.id === 'A')?.plannedQty).toBe(5)
    expect(res.rows.find((r) => r.id === 'B')?.plannedQty).toBe(2)
    expect(res.totals.totalCost).toBeCloseTo(900, 6)
    expect(res.totals.remaining).toBeCloseTo(100, 6)
  })

  it('computeWeightModeAllocation reports locked sum > 100 as error', () => {
    const res = computeWeightModeAllocation({
      funds: 1000,
      rows: rows([
        { id: 'A', w: 60, locked: true },
        { id: 'B', w: 50, locked: true },
      ]),
      pricesByRowId: { A: 100, B: 100 },
      requireWeightsSumTo100: true,
    })
    expect(res.issues.some((i) => i.code === 'locked_over_100')).toBe(true)
  })

  it('computeWeightModeAllocation requires weights sum to 100 when configured', () => {
    const res = computeWeightModeAllocation({
      funds: 1000,
      rows: rows([
        { id: 'A', w: 40 },
        { id: 'B', w: 40 },
      ]),
      pricesByRowId: { A: 100, B: 100 },
      requireWeightsSumTo100: true,
    })
    expect(res.issues.some((i) => i.code === 'weights_not_100')).toBe(true)
  })

  it('computeWeightModeAllocation can compute additional funds for min 1 share per symbol', () => {
    const res = computeWeightModeAllocation({
      funds: 1000,
      rows: rows([
        { id: 'A', w: 50 },
        { id: 'B', w: 50 },
      ]),
      pricesByRowId: { A: 1000, B: 100 },
      requireWeightsSumTo100: true,
      minQtyPerRow: 1,
    })
    expect(res.issues.some((i) => i.code === 'min_qty_funds_insufficient')).toBe(true)
    expect(res.totals.minFundsRequired).toBeCloseTo(2000, 6)
    expect(res.totals.additionalFundsRequired).toBeCloseTo(1000, 6)
    expect(
      res.rows.find((r) => r.id === 'A')?.issues.some((i) => i.code === 'min_qty_unmet' && i.level === 'error'),
    ).toBe(true)
  })

  it('computeWeightModeAllocation spends remaining funds to reduce underweight drift', () => {
    const res = computeWeightModeAllocation({
      funds: 1000,
      rows: rows([
        { id: 'A', w: 50 },
        { id: 'B', w: 50 },
      ]),
      pricesByRowId: { A: 90, B: 110 },
      requireWeightsSumTo100: true,
    })
    expect(res.rows.find((r) => r.id === 'A')?.plannedQty).toBe(5)
    expect(res.rows.find((r) => r.id === 'B')?.plannedQty).toBe(5)
    expect(res.totals.totalCost).toBeCloseTo(1000, 6)
    expect(res.totals.remaining).toBeCloseTo(0, 6)
  })

  it('computeWeightModeAllocation flags rounding outliers using IQR', () => {
    const res = computeWeightModeAllocation({
      funds: 10000,
      rows: rows([
        { id: 'A', w: 10 },
        { id: 'B', w: 10 },
        { id: 'C', w: 10 },
        { id: 'D', w: 10 },
        { id: 'E', w: 10 },
        { id: 'F', w: 10 },
        { id: 'G', w: 10 },
        { id: 'H', w: 10 },
        { id: 'I', w: 10 },
        { id: 'J', w: 10 },
      ]),
      pricesByRowId: {
        A: 333, // 3 shares => 999
        B: 9999, // outlier => 0 shares
        C: 250, // 4 shares => 1000
        D: 200, // 5 shares => 1000
        E: 180, // 5 shares => 900
        F: 167, // 5 shares => 835
        G: 150, // 6 shares => 900
        H: 125, // 8 shares => 1000
        I: 111, // 9 shares => 999
        J: 95, // 10 shares => 950
      },
      requireWeightsSumTo100: true,
      minQtyPerRow: 0,
      optimizeWithRemainingFunds: false,
    })
    expect(res.issues.some((i) => i.code === 'allocation_outliers')).toBe(true)
    expect(res.rows.some((r) => r.issues.some((i) => i.code === 'allocation_outlier'))).toBe(true)
  })
})
