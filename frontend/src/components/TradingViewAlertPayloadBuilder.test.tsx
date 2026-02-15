import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { TradingViewAlertPayloadBuilder } from './TradingViewAlertPayloadBuilder'

describe('TradingViewAlertPayloadBuilder', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the recommended alert message', async () => {
    render(<TradingViewAlertPayloadBuilder webhookSecret="my-secret" />)

    const input = screen.getByLabelText('TradingView alert message') as HTMLInputElement
    expect(input.value).toBe('{{strategy.order.alert_message}}')
  })

  it('copies the recommended alert message', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    render(<TradingViewAlertPayloadBuilder webhookSecret="my-secret" />)

    await user.click(screen.getByRole('button', { name: /^copy$/i }))
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('{{strategy.order.alert_message}}')
    })
  })
})
