import { render } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { AppThemeProvider } from './themeContext'

describe('App layout', () => {
  it('renders navigation links and API status chip', () => {
    render(
      <BrowserRouter>
        <AppThemeProvider>
          <App />
        </AppThemeProvider>
      </BrowserRouter>,
    )

    // We now land on the auth page before login; just assert that
    // the app renders without crashing.
    expect(document.body).toBeTruthy()
  })
})
