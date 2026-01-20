export type ParsedSymbol = {
  exchange: 'NSE' | 'BSE'
  symbol: string
  raw: string
}

export type ParseSymbolsResult = {
  items: ParsedSymbol[]
  errors: Array<{ raw: string; reason: string }>
}

function normalizeToken(raw: string): string {
  return (raw || '').trim().toUpperCase()
}

export function splitSymbolsText(text: string): string[] {
  return (text || '')
    .split(/[\n,]+/g)
    .map((s) => s.trim())
    .filter(Boolean)
}

export function parseSymbolToken(
  raw: string,
  defaultExchange: 'NSE' | 'BSE',
): { item?: ParsedSymbol; error?: { raw: string; reason: string } } {
  const token = normalizeToken(raw)
  if (!token) return { error: { raw, reason: 'empty' } }

  let exchange: 'NSE' | 'BSE' = defaultExchange
  let symbol = token

  if (token.includes(':')) {
    const [prefix, rest] = token.split(':', 2)
    if ((prefix === 'NSE' || prefix === 'BSE') && rest?.trim()) {
      exchange = prefix
      symbol = rest.trim()
    } else {
      return { error: { raw, reason: 'invalid_prefix' } }
    }
  }

  if (!symbol) return { error: { raw, reason: 'empty_symbol' } }
  return { item: { exchange, symbol, raw } }
}

export function parseSymbolsText(
  text: string,
  defaultExchange: 'NSE' | 'BSE',
): ParseSymbolsResult {
  const tokens = splitSymbolsText(text)
  const errors: Array<{ raw: string; reason: string }> = []
  const seen = new Set<string>()
  const items: ParsedSymbol[] = []

  for (const t of tokens) {
    const { item, error } = parseSymbolToken(t, defaultExchange)
    if (error) {
      errors.push(error)
      continue
    }
    if (!item) continue
    const key = `${item.exchange}:${item.symbol}`
    if (seen.has(key)) continue
    seen.add(key)
    items.push(item)
  }

  return { items, errors }
}

