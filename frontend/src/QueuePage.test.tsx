import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'

import { theme } from './theme'
import { QueuePage } from './views/QueuePage'

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
        <ThemeProvider theme={theme}>
          <QueuePage />
        </ThemeProvider>
      </BrowserRouter>,
    )

    expect(screen.getByText(/Waiting Queue/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('NSE:TCS')).toBeInTheDocument()
    })
  })
})
