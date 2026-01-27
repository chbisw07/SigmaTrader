import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { InstrumentSearch } from './InstrumentSearch'

describe('InstrumentSearch', () => {
  it('searches and calls onSelect with chosen instrument', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn()
    fetchMock.mockImplementation(async () => {
      return {
        ok: true,
        json: async () => [
          { symbol: 'INFY', exchange: 'NSE', tradingsymbol: 'INFY', name: 'Infosys Ltd', token: '1001' },
        ],
      } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    const onSelect = vi.fn()
    render(<InstrumentSearch onSelect={onSelect} />)

    const input = screen.getByLabelText('Quick trade') as HTMLInputElement
    await user.type(input, 'infy')

    await waitFor(() => expect(fetchMock).toHaveBeenCalled(), { timeout: 3000 })

    // Open options
    fireEvent.keyDown(input, { key: 'ArrowDown' })

    const opt = await screen.findByRole('option', { name: /NSE:.*INFY/i })
    fireEvent.click(opt)

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ symbol: 'INFY', exchange: 'NSE' }),
    )
  })
})
