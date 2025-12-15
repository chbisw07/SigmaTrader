import type { Holding } from '../services/positions'
import type {
  UniverseCapabilities,
  UniverseDefinition,
  UniverseSymbol,
} from './types'

export const HOLDINGS_UNIVERSE_ID = 'holdings'

export function createHoldingsUniverseDefinition(): UniverseDefinition {
  return {
    id: HOLDINGS_UNIVERSE_ID,
    kind: 'HOLDINGS',
    label: 'Holdings (Zerodha)',
    description: 'Live holdings fetched from Zerodha (Kite).',
  }
}

export function createHoldingsUniverseCapabilities(): UniverseCapabilities {
  return {
    supportsHoldingsOverlay: true,
    supportsShortSellMis: true,
  }
}

export function holdingsToUniverseSymbols(holdings: Holding[]): UniverseSymbol[] {
  return holdings.map((h) => ({
    symbol: h.symbol,
    exchange: h.exchange ?? null,
  }))
}

