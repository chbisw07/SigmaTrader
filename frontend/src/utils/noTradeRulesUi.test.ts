import { describe, expect, it } from 'vitest'

import {
  clearUiPauseAutoRule,
  extractUiPauseAutoWindow,
  setUiPauseAutoRule,
} from './noTradeRulesUi'

describe('noTradeRulesUi', () => {
  it('sets a tagged UI PAUSE_AUTO ALL rule', () => {
    const out = setUiPauseAutoRule('', '09:15', '09:30')
    expect(out).toContain('09:15-09:30 PAUSE_AUTO ALL')
    expect(out).toContain('# UI_PAUSE_AUTO')
  })

  it('replaces existing tagged rule without duplicating', () => {
    const a = setUiPauseAutoRule('09:15-09:30 PAUSE_AUTO ALL # UI_PAUSE_AUTO', '09:20', '09:40')
    const b = setUiPauseAutoRule(a, '09:25', '09:45')
    expect(b.match(/UI_PAUSE_AUTO/g)?.length ?? 0).toBe(1)
    expect(b).toContain('09:25-09:45 PAUSE_AUTO ALL')
  })

  it('clears tagged rule and preserves other lines', () => {
    const src = [
      '09:15-09:30 PAUSE_AUTO ALL # UI_PAUSE_AUTO',
      '09:15-09:30 PAUSE_AUTO BUY',
      '10:00-10:15 NO_TRADE MIS_SELL',
    ].join('\n')
    const out = clearUiPauseAutoRule(src)
    expect(out).not.toContain('UI_PAUSE_AUTO')
    expect(out).toContain('PAUSE_AUTO BUY')
    expect(out).toContain('NO_TRADE MIS_SELL')
  })

  it('extracts window from tagged rule', () => {
    const src = '09:15-09:30 PAUSE_AUTO ALL # UI_PAUSE_AUTO'
    expect(extractUiPauseAutoWindow(src)).toEqual({ start: '09:15', end: '09:30' })
  })
})

