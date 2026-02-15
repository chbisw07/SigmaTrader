import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DslExprHelpDrawer } from './DslExprHelpDrawer'

describe('DslExprHelpDrawer', () => {
  it('inserts a function signature when a row is clicked', async () => {
    const user = userEvent.setup()
    const onInsert = vi.fn()
    render(
      <DslExprHelpDrawer
        open
        onClose={() => {}}
        operands={['PNL_PCT']}
        customIndicators={[]}
        onInsert={onInsert}
      />,
    )

    await user.click(screen.getByText('SMA(close, 14, "1d")'))
    expect(onInsert).toHaveBeenCalledWith('SMA(close, 14, "1d")')
  })

  it('filters by search query', async () => {
    const user = userEvent.setup()
    const onInsert = vi.fn()
    render(
      <DslExprHelpDrawer
        open
        onClose={() => {}}
        operands={['PNL_PCT']}
        customIndicators={[]}
        onInsert={onInsert}
      />,
    )

    await user.type(screen.getByPlaceholderText(/search/i), 'CURRENT_VALUE')
    expect(screen.queryByText('SMA(close, 14, "1d")')).toBeNull()
    expect(screen.getAllByText('CURRENT_VALUE').length).toBeGreaterThan(0)
  })
})
