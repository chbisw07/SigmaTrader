import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'

import { HoldingsPage } from './views/HoldingsPage'
import { AppThemeProvider } from './themeContext'
import { TimeSettingsProvider } from './timeSettingsContext'

function okJson(data: unknown): Response {
  return {
    ok: true,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response
}

describe('HoldingsPage Quick trade', () => {
  beforeEach(() => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : input.toString()

      if (url.includes('/api/market/history')) return okJson([])
      if (url.includes('/api/zerodha/margins')) {
        return okJson({ available: 0, raw: {} })
      }

      if (url.includes('/api/risk-engine/symbol-categories')) return okJson([])
      if (url.includes('/api/groups/portfolio-allocations')) return okJson([])
      if (url.includes('/api/groups/')) return okJson([])
      if (url.includes('/api/holdings-goals/')) return okJson([])
      if (url.includes('/api/positions/daily')) return okJson([])
      if (url.includes('/api/positions/holdings')) {
        return okJson([
          {
            symbol: 'INFY',
            exchange: 'NSE',
            quantity: 1,
            average_price: 1000,
            last_price: 1100,
            pnl: 100,
            last_purchase_date: null,
            total_pnl_percent: 10,
            today_pnl_percent: 0,
            broker_name: 'zerodha',
          },
        ])
      }
      if (url.includes('/api/angelone/status')) return okJson({ connected: false })
      if (url.includes('/api/analytics/holdings-correlation')) {
        return okJson({
          symbols: [],
          matrix: [],
          window_days: 730,
          observations: 0,
          average_correlation: null,
          diversification_rating: 'N/A',
          summary: '',
          recommendations: [],
          top_positive: [],
          top_negative: [],
          symbol_stats: [],
          clusters: [],
          effective_independent_bets: null,
        })
      }

      if (url.includes('/api/instruments/search')) {
        return okJson([
          {
            symbol: 'INFY',
            exchange: 'NSE',
            tradingsymbol: 'INFY',
            name: 'Infosys Ltd',
            token: '1001',
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

  it('opens trade dialog with CNC default on instrument selection', async () => {
    const user = userEvent.setup()

    render(
      <BrowserRouter>
        <AppThemeProvider>
          <TimeSettingsProvider>
            <HoldingsPage />
          </TimeSettingsProvider>
        </AppThemeProvider>
      </BrowserRouter>,
    )

    const quickTradeInput = await screen.findByLabelText('Quick trade')
    await user.type(quickTradeInput, 'infy')
    await user.keyboard('{ArrowDown}')

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /NSE:.*INFY/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('option', { name: /NSE:.*INFY/i }))

    expect(await screen.findByText('NSE:INFY')).toBeInTheDocument()

    const product = screen.getByRole('combobox', { name: /product/i })
    expect(product).toHaveTextContent(/CNC/i)

    const infyRow = document.querySelector('[data-id="INFY"]')
    expect(infyRow).not.toBeNull()
    expect(infyRow!).toHaveClass('st-row-highlight')
  })
})
