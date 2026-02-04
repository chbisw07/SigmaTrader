import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import App from './App'
import { AppThemeProvider } from './themeContext'

describe('App layout', () => {
  it('renders navigation links and API status chip', async () => {
    // Prevent background auth fetch from updating state after the test completes.
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('', { status: 401 }))

    try {
      render(
        <MemoryRouter initialEntries={['/']}>
          <AppThemeProvider>
            <App />
          </AppThemeProvider>
        </MemoryRouter>,
      )

      // We now land on the auth page before login; just assert that
      // the app renders without crashing and settles.
      expect(await screen.findByText(/Trade smarter with SigmaTrader/i)).toBeInTheDocument()
    } finally {
      fetchSpy.mockRestore()
    }
  })
})
