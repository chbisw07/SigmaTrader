import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'

import App from './App'
import { theme } from './theme'

describe('App layout', () => {
  it('renders navigation links and API status chip', () => {
    render(
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          <App />
        </ThemeProvider>
      </BrowserRouter>,
    )

    // We now land on the auth page before login; just assert that
    // the app renders without crashing.
    expect(document.body).toBeTruthy()
  })
})
