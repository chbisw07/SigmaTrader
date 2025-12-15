import { describe, expect, it } from 'vitest'

import { resolvePrimaryPriceForHolding } from './tradePricing'

describe('resolvePrimaryPriceForHolding', () => {
  it('uses per-symbol bulk overrides (no cross-contamination)', () => {
    const overrides = { AAA: '10', BBB: '20' }

    const a = resolvePrimaryPriceForHolding({
      isBulkTrade: true,
      holding: { symbol: 'AAA', last_price: 11 },
      tradeOrderType: 'LIMIT',
      tradePrice: '9999',
      bulkPriceOverrides: overrides,
    })
    const b = resolvePrimaryPriceForHolding({
      isBulkTrade: true,
      holding: { symbol: 'BBB', last_price: 21 },
      tradeOrderType: 'LIMIT',
      tradePrice: '9999',
      bulkPriceOverrides: overrides,
    })

    expect(a).toBe(10)
    expect(b).toBe(20)
  })

  it('falls back to holding last_price when bulk override is missing', () => {
    const price = resolvePrimaryPriceForHolding({
      isBulkTrade: true,
      holding: { symbol: 'AAA', last_price: 11 },
      tradeOrderType: 'LIMIT',
      tradePrice: '9999',
      bulkPriceOverrides: {},
    })
    expect(price).toBe(11)
  })

  it('uses the explicit tradePrice for non-bulk non-market orders', () => {
    const price = resolvePrimaryPriceForHolding({
      isBulkTrade: false,
      holding: { symbol: 'AAA', last_price: 11 },
      tradeOrderType: 'LIMIT',
      tradePrice: '123.45',
      bulkPriceOverrides: {},
    })
    expect(price).toBe(123.45)
  })
})

