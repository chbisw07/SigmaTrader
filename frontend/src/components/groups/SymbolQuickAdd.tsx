import Autocomplete from '@mui/material/Autocomplete'
import Box from '@mui/material/Box'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useRef, useState } from 'react'

import { searchMarketSymbols, type MarketSymbol } from '../../services/marketData'
import { parseSymbolsText, type ParsedSymbol } from './symbolParsing'

export type SymbolQuickAddProps = {
  disabled?: boolean
  defaultExchange: 'NSE' | 'BSE'
  onDefaultExchangeChange: (exch: 'NSE' | 'BSE') => void
  onAddSymbols: (items: ParsedSymbol[]) => void
}

export function SymbolQuickAdd({
  disabled = false,
  defaultExchange,
  onDefaultExchangeChange,
  onAddSymbols,
}: SymbolQuickAddProps) {
  const [input, setInput] = useState('')
  const [options, setOptions] = useState<MarketSymbol[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const trimmed = input.trim()
  const canSubmit = !disabled && trimmed.length > 0

  const helperText = useMemo(() => {
    if (error) return error
    return 'Type a symbol and press Enter, or paste a comma/newline list.'
  }, [error])

  const submit = (rawText: string) => {
    const res = parseSymbolsText(rawText, defaultExchange)
    if (!res.items.length && res.errors.length) {
      setError(`Invalid input: ${res.errors[0]?.reason ?? 'invalid'}`)
      return
    }
    setError(null)
    if (res.items.length) onAddSymbols(res.items)
    setInput('')
  }

  const handlePaste = (txt: string) => {
    if (!txt) return
    if (!txt.includes('\n') && !txt.includes(',')) return
    submit(txt)
  }

  useEffect(() => {
    // If the input contains a list (comma/newline), treat it as a bulk paste
    // and submit immediately. This makes Ctrl+V feel instant and keeps the UI
    // simple (no separate bulk dialog).
    if (!input.includes('\n') && !input.includes(',')) return
    if (!input.trim()) return
    submit(input)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '/') return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const active = document.activeElement
      const tag = active ? (active as HTMLElement).tagName.toLowerCase() : ''
      if (tag === 'input' || tag === 'textarea' || (active as HTMLElement | null)?.isContentEditable) {
        return
      }
      e.preventDefault()
      inputRef.current?.focus()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    const q = input.trim()
    if (q.length < 1) {
      setOptions([])
      return
    }
    let active = true
    setLoading(true)
    const id = window.setTimeout(() => {
      void (async () => {
        try {
          const res = await searchMarketSymbols({
            q,
            exchange: defaultExchange,
            limit: 30,
          })
          if (!active) return
          setOptions(res)
        } catch (err) {
          if (!active) return
          setOptions([])
          setError(err instanceof Error ? err.message : 'Failed to search symbols')
        } finally {
          if (!active) return
          setLoading(false)
        }
      })()
    }, 200)
    return () => {
      active = false
      window.clearTimeout(id)
    }
  }, [defaultExchange, input])

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
      <TextField
        label="Exchange"
        size="small"
        select
        value={defaultExchange}
        onChange={(e) =>
          onDefaultExchangeChange(e.target.value === 'BSE' ? 'BSE' : 'NSE')
        }
        sx={{ width: { xs: '100%', md: 120 } }}
        disabled={disabled}
      >
        <MenuItem value="NSE">NSE</MenuItem>
        <MenuItem value="BSE">BSE</MenuItem>
      </TextField>

      <Autocomplete<MarketSymbol, false, false, true>
        freeSolo
        clearOnBlur={false}
        options={options}
        loading={loading}
        value={null}
        inputValue={input}
        onInputChange={(_e, value) => setInput(value)}
        getOptionLabel={(o) => (typeof o === 'string' ? o : o.symbol)}
        renderOption={(props, option) => (
          <li {...props} key={`${option.exchange}:${option.symbol}`}>
            <Box sx={{ display: 'flex', flexDirection: 'column' }}>
              <Typography variant="body2">
                {option.symbol}{' '}
                <Typography component="span" variant="caption" color="text.secondary">
                  ({option.exchange})
                </Typography>
              </Typography>
              {option.name ? (
                <Typography variant="caption" color="text.secondary">
                  {option.name}
                </Typography>
              ) : null}
            </Box>
          </li>
        )}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Add symbols"
            size="small"
            sx={{ width: { xs: '100%', md: 360 } }}
            helperText={helperText}
            error={!!error}
            inputRef={(el) => {
              inputRef.current = el
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && canSubmit) {
                e.preventDefault()
                submit(input)
              }
            }}
            InputProps={{
              ...params.InputProps,
            }}
            inputProps={{
              ...params.inputProps,
              onPaste: (e) => {
                const txt = e.clipboardData?.getData('text') ?? ''
                if (txt.includes('\n') || txt.includes(',')) {
                  e.preventDefault()
                  handlePaste(txt)
                  return
                }
                // MUI types `onPaste` broadly (input or textarea); we only use
                // input events here, so cast to keep TS happy.
                ;(params.inputProps.onPaste as unknown as ((ev: typeof e) => void) | undefined)?.(
                  e,
                )
              },
            }}
          />
        )}
      />
    </Stack>
  )
}
