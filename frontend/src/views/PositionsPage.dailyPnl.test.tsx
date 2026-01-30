import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

import { PositionsPage } from './PositionsPage'
import { AppThemeProvider } from '../themeContext'
import { TimeSettingsProvider } from '../timeSettingsContext'

function okJson(data: unknown): Response {
  return {
    ok: true,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response
}

describe('PositionsPage daily snapshots P&L', () => {
  beforeEach(() => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : input.toString()

      if (url.includes('/api/brokers/')) {
        return okJson([{ name: 'zerodha', label: 'Zerodha (Kite)' }])
      }

      if (url.includes('/api/positions/daily')) {
        return okJson([
          {
            id: 1,
            as_of_date: '2026-01-29',
            captured_at: new Date().toISOString(),
            symbol: 'ASTRAMICRO',
            exchange: 'NSE',
            product: 'CNC',
            qty: -31,
            remaining_qty: 0,
            traded_qty: 62,
            order_type: 'SELL',
            avg_price: 969.35,
            pnl: 0,
            avg_buy_price: 957.9,
            avg_sell_price: 969.35,
            pnl_value: 354.95,
            pnl_pct: 1.195,
            ltp: 971.55,
            today_pnl: 0,
            today_pnl_pct: 0,
          },
        ])
      }

      return okJson([])
    })

    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows P&L and P&L% when buy/sell avg present', async () => {
    render(
      <BrowserRouter>
        <AppThemeProvider>
          <TimeSettingsProvider>
            <PositionsPage />
          </TimeSettingsProvider>
        </AppThemeProvider>
      </BrowserRouter>,
    )

    await screen.findByText('ASTRAMICRO')
    await screen.findByText('354.95')
    await screen.findByText('1.20%')
  })
})
