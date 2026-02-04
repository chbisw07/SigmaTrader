import { describe, expect, it } from 'vitest'

import { formatOrderTypePolicyTokens, parseOrderTypePolicyTokens } from './orderTypePolicy'

describe('orderTypePolicy', () => {
  it('parses comma/semicolon separated policy', () => {
    expect(parseOrderTypePolicyTokens('market; limit, sl')).toEqual(['MARKET', 'LIMIT', 'SL'])
  })

  it('formats tokens into a stable allowlist', () => {
    expect(formatOrderTypePolicyTokens(['limit', 'market', 'limit'])).toBe('MARKET,LIMIT')
  })

  it('returns null for empty tokens', () => {
    expect(formatOrderTypePolicyTokens([])).toBeNull()
  })
})

