import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { AppThemeProvider } from '../../themeContext'
import { SymbolQuickAdd } from './SymbolQuickAdd'

describe('SymbolQuickAdd', () => {
  beforeEach(() => {
    const fetchMock = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/api/market/symbols')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      return { ok: false, text: async () => 'not found' } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('submits a single symbol on Enter', async () => {
    const onAddSymbols = vi.fn()
    const onDefaultExchangeChange = vi.fn()

    render(
      <AppThemeProvider>
        <SymbolQuickAdd
          defaultExchange="NSE"
          onDefaultExchangeChange={onDefaultExchangeChange}
          onAddSymbols={onAddSymbols}
        />
      </AppThemeProvider>,
    )

    const input = screen.getByLabelText('Add symbols') as HTMLInputElement
    await userEvent.type(input, 'TCS{enter}')

    await waitFor(() => {
      expect(onAddSymbols).toHaveBeenCalledTimes(1)
    })
    expect(onAddSymbols.mock.calls[0]?.[0]).toEqual([
      { exchange: 'NSE', symbol: 'TCS', raw: 'TCS' },
    ])
  })

  it('submits a pasted list', async () => {
    const onAddSymbols = vi.fn()
    const onDefaultExchangeChange = vi.fn()

    render(
      <AppThemeProvider>
        <SymbolQuickAdd
          defaultExchange="NSE"
          onDefaultExchangeChange={onDefaultExchangeChange}
          onAddSymbols={onAddSymbols}
        />
      </AppThemeProvider>,
    )

    const input = screen.getByLabelText('Add symbols') as HTMLInputElement
    fireEvent.paste(input, {
      clipboardData: { getData: () => 'TCS\nINFY\nTCS' },
    })

    await waitFor(() => {
      expect(onAddSymbols).toHaveBeenCalledTimes(1)
    })
    expect(onAddSymbols.mock.calls[0]?.[0]).toEqual([
      { exchange: 'NSE', symbol: 'TCS', raw: 'TCS' },
      { exchange: 'NSE', symbol: 'INFY', raw: 'INFY' },
    ])
  })
})
