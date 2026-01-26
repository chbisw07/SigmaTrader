import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  TradingViewAlertPayloadBuilder,
  buildTradingViewAlertPayloadJson,
  DEFAULT_SIGNAL,
  DEFAULT_SIGNAL_ENABLED,
} from './TradingViewAlertPayloadBuilder'

describe('TradingViewAlertPayloadBuilder', () => {
  beforeEach(() => {
    // Clipboard API is unreliable in jsdom; tests focus on the generated JSON.
    vi.restoreAllMocks()
  })

  it('masks secret in preview but copies unmasked secret', async () => {
    render(<TradingViewAlertPayloadBuilder webhookSecret="my-secret" />)

    const preview = screen.getByLabelText('json-preview')
    expect(preview.textContent).toContain('"secret": "********"')
    expect(preview.textContent).not.toContain('my-secret')
    expect(preview.textContent).toContain('"price": {{close}}')

    // The copy payload must contain the real secret and preserve raw numeric tokens.
    const copied = buildTradingViewAlertPayloadJson({
      secret: 'my-secret',
      maskSecret: false,
      signal: DEFAULT_SIGNAL,
      signalEnabled: DEFAULT_SIGNAL_ENABLED,
      hints: [],
    })
    expect(copied).toContain('"secret": "my-secret"')
    expect(copied).not.toContain('"secret": "********"')
    expect(copied).toContain('"price": {{close}}')
  })

  it('validates hint keys and disables copy when invalid', async () => {
    const user = userEvent.setup()
    render(<TradingViewAlertPayloadBuilder webhookSecret="my-secret" />)

    const copyBtn = screen.getByRole('button', { name: /copy json/i })
    expect(copyBtn).toBeEnabled()

    await user.click(screen.getByRole('button', { name: /\+ add field/i }))

    const keyInput = screen.getByLabelText('hint-key-0')
    await user.clear(keyInput)
    await user.type(keyInput, 'bad key')

    expect(copyBtn).toBeDisabled()
    expect(screen.getByText(/key must match/i)).toBeInTheDocument()

    await user.clear(keyInput)
    await user.type(keyInput, 'note')
    expect(copyBtn).toBeEnabled()
  })
})
