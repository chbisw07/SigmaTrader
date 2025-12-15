export type TradeSide = 'BUY' | 'SELL'
export type TradeProduct = 'CNC' | 'MIS'

export function shouldClampSellToHoldingsQty(params: {
  side: TradeSide
  product: TradeProduct
}): boolean {
  return params.side === 'SELL' && params.product === 'CNC'
}

export function clampQtyToMax(qty: number, maxQty: number): number {
  if (!Number.isFinite(qty)) return 0
  if (!Number.isFinite(maxQty)) return qty
  if (maxQty < 0) return 0
  return qty > maxQty ? maxQty : qty
}

