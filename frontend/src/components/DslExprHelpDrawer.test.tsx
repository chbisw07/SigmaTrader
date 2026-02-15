import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DslExprHelpDrawer } from './DslExprHelpDrawer'

describe('DslExprHelpDrawer', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('loads and inserts user-defined entries', async () => {
    const user = userEvent.setup()
    const onInsert = vi.fn()
    window.localStorage.setItem(
      'st_dsl_catalog_user_items_v1',
      JSON.stringify([
        { expr: 'MY_SNIP', signature: 'SMA(close, 20, "1d")', details: 'test' },
      ]),
    )
    render(
      <DslExprHelpDrawer
        open
        onClose={() => {}}
        operands={[]}
        customIndicators={[]}
        onInsert={onInsert}
      />,
    )

    await user.click(screen.getByText('User'))
    await user.click(screen.getByText('SMA(close, 20, "1d")'))
    expect(onInsert).toHaveBeenCalledWith('SMA(close, 20, "1d")')
  })

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
