export const ORDER_TYPE_OPTIONS = ['MARKET', 'LIMIT', 'SL', 'SL-M'] as const

function splitOrderTypePolicy(v: string | null | undefined): string[] {
  const raw = String(v ?? '').trim()
  if (!raw) return []
  return raw
    .replace(/;/g, ',')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function normalizeTokens(tokens: readonly string[]): string[] {
  const seen = new Set<string>()
  const unique: string[] = []
  for (const t of tokens) {
    const u = String(t ?? '').trim().toUpperCase()
    if (!u || seen.has(u)) continue
    seen.add(u)
    unique.push(u)
  }

  const knownOrder = new Map<string, number>()
  for (let i = 0; i < ORDER_TYPE_OPTIONS.length; i++) knownOrder.set(ORDER_TYPE_OPTIONS[i], i)

  const known: string[] = []
  const unknown: string[] = []
  for (const t of unique) (knownOrder.has(t) ? known : unknown).push(t)
  known.sort((a, b) => (knownOrder.get(a) ?? 0) - (knownOrder.get(b) ?? 0))
  return [...known, ...unknown]
}

export function parseOrderTypePolicyTokens(v: string | null | undefined): string[] {
  return normalizeTokens(splitOrderTypePolicy(v))
}

export function formatOrderTypePolicyTokens(tokens: readonly string[]): string | null {
  const normalized = normalizeTokens(tokens)
  return normalized.length ? normalized.join(',') : null
}

