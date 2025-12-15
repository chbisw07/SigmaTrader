export type UniverseKind =
  | 'HOLDINGS'
  | 'WATCHLIST'
  | 'BASKET'
  | 'PORTFOLIO'
  | 'HOLDINGS_VIEW'

export type UniverseId = string

export type UniverseDefinition = {
  id: UniverseId
  kind: UniverseKind
  label: string
  description?: string | null
}

export type UniverseSymbol = {
  symbol: string
  exchange?: string | null
  notes?: string | null
  target_weight?: number | null
}

export type UniverseCapabilities = {
  supportsHoldingsOverlay: boolean
  supportsShortSellMis: boolean
}

