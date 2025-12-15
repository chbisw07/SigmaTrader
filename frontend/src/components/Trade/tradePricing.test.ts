import { describe, expect, it } from 'vitest'

import { resolvePrimaryPriceForHolding } from './tradePricing'

describe('resolvePrimaryPriceForHolding', () => {
  it('does not reuse tradePrice across symbols in bulk mode', () => {
    const price = resolvePrimaryPriceForHolding({
      isBulkTrade: true,
      holding: { symbol: 'AAA', last_price: 684.4 },
      tradeOrderType: 'LIMIT',
      tradePrice: '679.60',
      bulkPriceOverrides: {},
    })
    expect(price).toBe(684.4)
  })

  it('uses per-holding override price in bulk mode', () => {
    const price = resolvePrimaryPriceForHolding({
      isBulkTrade: true,
      holding: { symbol: 'AAA', last_price: 684.4 },
      tradeOrderType: 'LIMIT',
      tradePrice: '679.60',
      bulkPriceOverrides: { AAA: '700.25' },
    })
    expect(price).toBe(700.25)
  })

  it('uses typed tradePrice for single-symbol LIMIT orders', () => {
    const price = resolvePrimaryPriceForHolding({
      isBulkTrade: false,
      holding: { symbol: 'AAA', last_price: 684.4 },
      tradeOrderType: 'LIMIT',
      tradePrice: '679.60',
      bulkPriceOverrides: {},
    })
    expect(price).toBe(679.6)
  })

  it('ignores typed tradePrice for single-symbol MARKET orders', () => {
    const price = resolvePrimaryPriceForHolding({
      isBulkTrade: false,
      holding: { symbol: 'AAA', last_price: 684.4 },
      tradeOrderType: 'MARKET',
      tradePrice: '679.60',
      bulkPriceOverrides: {},
    })
    expect(price).toBe(684.4)
  })
})

