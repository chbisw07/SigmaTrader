import { describe, expect, it } from 'vitest'

import { resolveSymbolRiskCategory } from './symbolRiskCategories'

describe('resolveSymbolRiskCategory', () => {
  it('prefers latest updated row among broker/exchange wildcards', () => {
    const rows = [
      {
        id: 1,
        user_id: 1,
        broker_name: 'zerodha',
        exchange: 'NSE',
        symbol: 'TCS',
        risk_category: 'MC',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 2,
        user_id: 1,
        broker_name: '*',
        exchange: '*',
        symbol: 'TCS',
        risk_category: 'LC',
        created_at: '2026-01-02T00:00:00Z',
        updated_at: '2026-01-03T00:00:00Z',
      },
    ] as any

    expect(resolveSymbolRiskCategory(rows, { broker_name: 'angelone', exchange: 'BSE', symbol: 'TCS' })).toBe('LC')
    expect(resolveSymbolRiskCategory(rows, { broker_name: 'zerodha', exchange: 'NSE', symbol: 'TCS' })).toBe('LC')
  })
})

