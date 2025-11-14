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

    expect(screen.getAllByText(/Dashboard/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Queue/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Orders/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Analytics/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Settings/i).length).toBeGreaterThan(0)

    expect(screen.getByText(/API:/i)).toBeInTheDocument()
  })
})
