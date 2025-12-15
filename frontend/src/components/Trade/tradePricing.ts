export type TradeOrderType = 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'

export type HoldingPricingLike = {
  symbol: string
  last_price?: number | null
  average_price?: number | null
}

const parsePositiveNumber = (value: string): number | null => {
  const num = Number(value)
  return Number.isFinite(num) && num > 0 ? num : null
}

export const getHoldingDisplayPrice = (
  holding: HoldingPricingLike | null,
): number | null => {
  if (!holding) return null
  const last = holding.last_price != null ? Number(holding.last_price) : null
  if (last != null && Number.isFinite(last) && last > 0) return last
  const avg =
    holding.average_price != null ? Number(holding.average_price) : null
  if (avg != null && Number.isFinite(avg) && avg > 0) return avg
  return null
}

export const resolvePrimaryPriceForHolding = (args: {
  isBulkTrade: boolean
  holding: HoldingPricingLike | null
  tradeOrderType: TradeOrderType
  tradePrice: string
  bulkPriceOverrides: Record<string, string | undefined>
}): number | null => {
  const { isBulkTrade, holding, tradeOrderType, tradePrice, bulkPriceOverrides } =
    args

  if (isBulkTrade && holding) {
    const override = bulkPriceOverrides[holding.symbol]
    if (override != null && override.trim() !== '') {
      const parsed = parsePositiveNumber(override.trim())
      if (parsed != null) return parsed
    }
    return getHoldingDisplayPrice(holding)
  }

  if (!isBulkTrade && tradeOrderType !== 'MARKET' && tradePrice.trim() !== '') {
    const parsed = parsePositiveNumber(tradePrice.trim())
    if (parsed != null) return parsed
  }

  return getHoldingDisplayPrice(holding)
}

