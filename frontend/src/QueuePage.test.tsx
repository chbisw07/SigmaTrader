import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

import { QueuePage } from './views/QueuePage'
import { AppThemeProvider } from './themeContext'

describe('QueuePage', () => {
  beforeEach(() => {
    const fetchMock = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/api/brokers/capabilities')) {
        return {
          ok: true,
          json: async () => [
            {
              name: 'zerodha',
              label: 'Zerodha (Kite)',
              capabilities: {
                supports_gtt: true,
                supports_conditional_orders: true,
                supports_margin_preview: true,
                supports_order_preview: true,
                supports_ltp: true,
              },
            },
          ],
        } as unknown as Response
      }
      if (url.includes('/api/orders/queue')) {
        return {
          ok: true,
          json: async () => [
            {
              id: 1,
              alert_id: 1,
              strategy_id: null,
              symbol: 'NSE:TCS',
              exchange: 'NSE',
              side: 'BUY',
              qty: 3,
              price: 3500,
              order_type: 'MARKET',
              product: 'MIS',
              gtt: false,
              status: 'WAITING',
              mode: 'MANUAL',
              simulated: false,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          ],
        } as unknown as Response
      }
      return { ok: false, text: async () => 'not found' } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders queue table with orders', async () => {
    render(
      <BrowserRouter>
        <AppThemeProvider>
          <QueuePage />
        </AppThemeProvider>
      </BrowserRouter>,
    )

    expect(screen.getByText(/Waiting Queue/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('NSE:TCS')).toBeInTheDocument()
    })
  })
})
