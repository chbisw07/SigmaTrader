import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

import { AppThemeProvider } from '../themeContext'
import { RiskManagementGuidePage } from './RiskManagementGuidePage'

describe('RiskManagementGuidePage', () => {
  it('renders guide and key sections', () => {
    render(
      <BrowserRouter>
        <AppThemeProvider>
          <RiskManagementGuidePage />
        </AppThemeProvider>
      </BrowserRouter>,
    )

    expect(screen.getByText('Risk Management Guide')).toBeInTheDocument()
    expect(screen.getAllByText('SigmaTrader vs broker enforcement').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Glossary: reason codes').length).toBeGreaterThan(0)
  })
})
