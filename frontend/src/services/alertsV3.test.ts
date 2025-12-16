import { testAlertExpression } from './alertsV3'

function okJson(data: unknown): Response {
  return {
    ok: true,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response
}

describe('alertsV3 service', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts to /api/alerts-v3/test with limit and payload', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      expect(url).toContain('/api/alerts-v3/test')
      expect(url).toContain('limit=25')
      expect(init?.method).toBe('POST')
      expect(init?.headers).toEqual({ 'Content-Type': 'application/json' })

      const body = JSON.parse(String(init?.body)) as any
      expect(body.target_kind).toBe('SYMBOL')
      expect(body.target_ref).toBe('TEST')
      expect(body.condition_dsl).toBe('PRICE(\"1d\") > 100')
      return okJson({
        evaluation_cadence: '1d',
        results: [],
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const res = await testAlertExpression(
      {
        target_kind: 'SYMBOL',
        target_ref: 'TEST',
        exchange: 'NSE',
        evaluation_cadence: '',
        variables: [],
        condition_dsl: 'PRICE(\"1d\") > 100',
      },
      { limit: 25 },
    )

    expect(res.evaluation_cadence).toBe('1d')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

