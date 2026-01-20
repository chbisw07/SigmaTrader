import { describe, expect, it } from 'vitest'

import { parseSymbolsText, parseSymbolToken, splitSymbolsText } from './symbolParsing'

describe('symbolParsing', () => {
  it('splits by comma/newline', () => {
    expect(splitSymbolsText('TCS, INFY\nHDFCBANK')).toEqual(['TCS', 'INFY', 'HDFCBANK'])
  })

  it('parses NSE:/BSE: prefixes', () => {
    expect(parseSymbolToken('nse:tcs', 'NSE').item).toEqual({
      exchange: 'NSE',
      symbol: 'TCS',
      raw: 'nse:tcs',
    })
    expect(parseSymbolToken('BSE:500180', 'NSE').item).toEqual({
      exchange: 'BSE',
      symbol: '500180',
      raw: 'BSE:500180',
    })
  })

  it('rejects unknown prefixes when colon is present', () => {
    expect(parseSymbolToken('FOO:BAR', 'NSE').error?.reason).toBe('invalid_prefix')
  })

  it('dedupes items by exchange+symbol', () => {
    const res = parseSymbolsText('TCS\nNSE:TCS\nBSE:TCS', 'NSE')
    expect(res.items.map((i) => `${i.exchange}:${i.symbol}`)).toEqual(['NSE:TCS', 'BSE:TCS'])
  })
})

