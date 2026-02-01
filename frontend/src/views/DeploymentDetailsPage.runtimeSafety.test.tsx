import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { AppThemeProvider } from '../themeContext'
import { TimeSettingsProvider } from '../timeSettingsContext'
import { DeploymentDetailsPage } from './DeploymentDetailsPage'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppThemeProvider>
        <TimeSettingsProvider>
          <Routes>
            <Route path="/deployments/:id" element={<DeploymentDetailsPage />} />
          </Routes>
        </TimeSettingsProvider>
      </AppThemeProvider>
    </MemoryRouter>,
  )
}

describe('DeploymentDetailsPage runtime safety', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('requires confirmation before starting SHORT deployments', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.endsWith('/api/deployments/1') && (!init || init.method === undefined)) {
        return {
          ok: true,
          json: async () => ({
            id: 1,
            owner_id: 1,
            name: 'short_dep',
            description: null,
            kind: 'STRATEGY',
            enabled: false,
            universe: { target_kind: 'SYMBOL', symbols: [{ exchange: 'NSE', symbol: 'INFY' }] },
            config: {
              timeframe: '1m',
              entry_dsl: 'PRICE(1d) > 0',
              exit_dsl: 'PRICE(1d) > 0',
              product: 'MIS',
              direction: 'SHORT',
              acknowledge_short_risk: true,
              broker_name: 'zerodha',
              execution_target: 'PAPER',
            },
            state: { status: 'STOPPED' },
            state_summary: { open_positions: 0, positions: [] },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }),
        } as unknown as Response
      }
      if (url.includes('/api/deployments/1/actions')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      if (url.endsWith('/api/deployments/1/jobs/metrics')) {
        return {
          ok: true,
          json: async () => ({ job_counts: {}, oldest_pending_scheduled_for: null, latest_failed_updated_at: null }),
        } as unknown as Response
      }
      if (url.endsWith('/api/deployments/1/start') && init?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            id: 1,
            owner_id: 1,
            name: 'short_dep',
            description: null,
            kind: 'STRATEGY',
            enabled: true,
            universe: { target_kind: 'SYMBOL', symbols: [{ exchange: 'NSE', symbol: 'INFY' }] },
            config: {
              timeframe: '1m',
              entry_dsl: 'PRICE(1d) > 0',
              exit_dsl: 'PRICE(1d) > 0',
              product: 'MIS',
              direction: 'SHORT',
              acknowledge_short_risk: true,
              broker_name: 'zerodha',
              execution_target: 'PAPER',
            },
            state: { status: 'RUNNING', exposure: { symbols: [] } },
            state_summary: { open_positions: 0, positions: [] },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }),
        } as unknown as Response
      }
      return { ok: false, text: async () => 'not found' } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    renderAt('/deployments/1')

    await waitFor(() => {
      expect(screen.getByText(/Deployment #1/i)).toBeInTheDocument()
    })

    const startBtn = await screen.findByRole('button', { name: /Start/i })
    await user.click(startBtn)

    expect(await screen.findByText(/Start deployment/i)).toBeInTheDocument()
    const confirmBtn = screen.getByRole('button', { name: /Confirm/i })
    expect(confirmBtn).toBeDisabled()

    const ack = screen.getByLabelText(/short-selling risks/i)
    await user.click(ack)
    expect(confirmBtn).toBeEnabled()

    await user.click(confirmBtn)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/deployments/1/start',
      expect.objectContaining({ method: 'POST' }),
    )
  }, 15000)

  it('shows direction mismatch actions and calls resolve endpoint', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.endsWith('/api/deployments/1') && (!init || init.method === undefined)) {
        return {
          ok: true,
          json: async () => ({
            id: 1,
            owner_id: 1,
            name: 'mismatch_dep',
            description: null,
            kind: 'STRATEGY',
            enabled: true,
            universe: { target_kind: 'SYMBOL', symbols: [{ exchange: 'NSE', symbol: 'INFY' }] },
            config: {
              timeframe: '1m',
              entry_dsl: 'PRICE(1d) > 0',
              exit_dsl: 'PRICE(1d) > 0',
              product: 'MIS',
              direction: 'LONG',
              broker_name: 'zerodha',
              execution_target: 'LIVE',
            },
            state: {
              status: 'PAUSED',
              runtime_state: 'PAUSED_DIRECTION_MISMATCH',
              exposure: {
                symbols: [
                  {
                    exchange: 'NSE',
                    symbol: 'INFY',
                    broker_net_qty: -2,
                    broker_side: 'SHORT',
                    deployments_net_qty: 0,
                    deployments_side: 'FLAT',
                    combined_net_qty: -2,
                    combined_side: 'SHORT',
                  },
                ],
              },
            },
            state_summary: { open_positions: 0, positions: [] },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }),
        } as unknown as Response
      }
      if (url.includes('/api/deployments/1/actions')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      if (url.endsWith('/api/deployments/1/jobs/metrics')) {
        return {
          ok: true,
          json: async () => ({ job_counts: {}, oldest_pending_scheduled_for: null, latest_failed_updated_at: null }),
        } as unknown as Response
      }
      if (url.endsWith('/api/deployments/1/direction-mismatch/resolve') && init?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            id: 1,
            owner_id: 1,
            name: 'mismatch_dep',
            description: null,
            kind: 'STRATEGY',
            enabled: true,
            universe: { target_kind: 'SYMBOL', symbols: [{ exchange: 'NSE', symbol: 'INFY' }] },
            config: {
              timeframe: '1m',
              entry_dsl: 'PRICE(1d) > 0',
              exit_dsl: 'PRICE(1d) > 0',
              product: 'MIS',
              direction: 'LONG',
              broker_name: 'zerodha',
              execution_target: 'LIVE',
            },
            state: { status: 'RUNNING' },
            state_summary: { open_positions: 0, positions: [] },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }),
        } as unknown as Response
      }
      return { ok: false, text: async () => 'not found' } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    renderAt('/deployments/1')

    await waitFor(() => {
      expect(screen.getByText(/Direction mismatch detected/i)).toBeInTheDocument()
    })

    const adoptBtn = screen.getByRole('button', { name: /Adopt \(exit-only\)/i })
    await user.click(adoptBtn)

    expect(await screen.findByText(/Resolve direction mismatch/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Confirm/i }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/deployments/1/direction-mismatch/resolve',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
