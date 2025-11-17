import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

import { QueuePage } from './views/QueuePage'
import { AppThemeProvider } from './themeContext'

describe('QueuePage', () => {
  beforeEach(() => {
    const fetchMock = vi.fn()
    fetchMock.mockResolvedValueOnce({
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
    } as any)
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
