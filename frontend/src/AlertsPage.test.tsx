import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'

import { AlertsPage } from './views/AlertsPage'
import { AppThemeProvider } from './themeContext'

function okJson(data: unknown): Response {
  return {
    ok: true,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response
}

describe('AlertsPage (v3)', () => {
  beforeEach(() => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()

      if (url.includes('/api/alerts-v3/events/')) {
        return okJson([
          {
            id: 1,
            alert_definition_id: 42,
            symbol: 'TEST',
            exchange: 'NSE',
            evaluation_cadence: '1d',
            reason: 'Matched: PRICE("1d") > 100',
            snapshot: { LHS: 106, RHS: 100 },
            triggered_at: new Date().toISOString(),
            bar_time: new Date().toISOString(),
          },
        ])
      }

      if (url.endsWith('/api/alerts-v3/')) {
        return okJson([
          {
            id: 42,
            name: 'My alert',
            target_kind: 'SYMBOL',
            target_ref: 'TEST',
            exchange: 'NSE',
            action_type: 'ALERT_ONLY',
            action_params: {},
            evaluation_cadence: '1d',
            variables: [],
            condition_dsl: 'PRICE("1d") > 100',
            trigger_mode: 'ONCE_PER_BAR',
            throttle_seconds: null,
            only_market_hours: false,
            expires_at: null,
            enabled: true,
            last_evaluated_at: null,
            last_triggered_at: null,
            created_at: null,
            updated_at: null,
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

  it('shows event snapshot JSON and links back to alert editor', async () => {
    const user = userEvent.setup()

    render(
      <BrowserRouter>
        <AppThemeProvider>
          <AlertsPage />
        </AppThemeProvider>
      </BrowserRouter>,
    )

    await user.click(screen.getByRole('tab', { name: /events/i }))

    expect(
      await screen.findByText(/trigger history/i),
    ).toBeInTheDocument()

    const details = await screen.findByRole('button', { name: /details/i })
    await user.click(details)

    expect(
      await screen.findByText(/event snapshot/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/"LHS": 106/i)).toBeInTheDocument()
    expect(screen.getByText(/"RHS": 100/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /open alert/i }))

    await waitFor(() => {
      expect(screen.getByText(/edit alert/i)).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Name')).toHaveValue('My alert')
  })
})
