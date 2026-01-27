import SearchIcon from '@mui/icons-material/Search'
import Autocomplete from '@mui/material/Autocomplete'
import Box from '@mui/material/Box'
import InputAdornment from '@mui/material/InputAdornment'
import ListItemText from '@mui/material/ListItemText'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useRef, useState } from 'react'

import { searchInstruments, type InstrumentSearchResult } from '../services/instruments'

type InstrumentSearchProps = {
  label?: string
  brokerName?: string
  exchange?: string | null
  limit?: number
  recentKey?: string
  onSelect: (instrument: InstrumentSearchResult) => void
}

function normalizeQ(q: string): string {
  return q.trim()
}

function highlight(text: string, q: string): React.ReactNode {
  const query = q.trim()
  if (!query) return text
  const lower = text.toLowerCase()
  const lowerQ = query.toLowerCase()
  const idx = lower.indexOf(lowerQ)
  if (idx < 0) return text
  const before = text.slice(0, idx)
  const match = text.slice(idx, idx + query.length)
  const after = text.slice(idx + query.length)
  return (
    <>
      {before}
      <Box component="mark" sx={{ backgroundColor: 'warning.light', px: 0.25, borderRadius: 0.5 }}>
        {match}
      </Box>
      {after}
    </>
  )
}

function readRecent(recentKey: string): InstrumentSearchResult[] {
  try {
    const raw = window.localStorage.getItem(recentKey)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter((x) => x && typeof x.symbol === 'string' && typeof x.exchange === 'string')
  } catch {
    return []
  }
}

function writeRecent(recentKey: string, inst: InstrumentSearchResult): void {
  try {
    const current = readRecent(recentKey)
    const key = `${inst.exchange}:${inst.symbol}`
    const deduped = [inst, ...current.filter((x) => `${x.exchange}:${x.symbol}` !== key)]
    window.localStorage.setItem(recentKey, JSON.stringify(deduped.slice(0, 5)))
  } catch {
    // ignore
  }
}

export function InstrumentSearch(props: InstrumentSearchProps) {
  const {
    label = 'Quick trade',
    brokerName = 'zerodha',
    exchange = null,
    limit = 20,
    recentKey = 'st_quick_trade_recent_v1',
    onSelect,
  } = props

  const [open, setOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [value, setValue] = useState<InstrumentSearchResult | null>(null)
  const [options, setOptions] = useState<InstrumentSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lastAbort = useRef<AbortController | null>(null)
  const debounceTimer = useRef<number | null>(null)

  const q = useMemo(() => normalizeQ(inputValue), [inputValue])

  const recentOptions = useMemo(() => readRecent(recentKey), [recentKey])

  useEffect(() => {
    if (debounceTimer.current != null) window.clearTimeout(debounceTimer.current)
    if (lastAbort.current) lastAbort.current.abort()

    if (!q) {
      setOptions(recentOptions)
      setLoading(false)
      setError(null)
      return
    }

    debounceTimer.current = window.setTimeout(() => {
      const controller = new AbortController()
      lastAbort.current = controller
      setLoading(true)
      void (async () => {
        try {
          const rows = await searchInstruments({
            q,
            broker_name: brokerName,
            exchange,
            limit,
            signal: controller.signal,
          })
          setOptions(rows)
          setError(null)
        } catch (e) {
          if ((e as any)?.name === 'AbortError') return
          setError(e instanceof Error ? e.message : 'Failed to search instruments')
          setOptions([])
        } finally {
          setLoading(false)
        }
      })()
    }, 300)

    return () => {
      if (debounceTimer.current != null) window.clearTimeout(debounceTimer.current)
      if (lastAbort.current) lastAbort.current.abort()
    }
  }, [q, brokerName, exchange, limit, recentOptions])

  return (
    <Autocomplete
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      value={value}
      onChange={(_e, next) => {
        setValue(next)
        if (next) {
          writeRecent(recentKey, next)
          onSelect(next)
          setInputValue('')
          setOpen(false)
          setValue(null)
        }
      }}
      inputValue={inputValue}
      onInputChange={(_e, next) => setInputValue(next)}
      options={options}
      loading={loading}
      getOptionLabel={(opt) => `${opt.exchange}:${opt.symbol}`}
      isOptionEqualToValue={(a, b) => a.symbol === b.symbol && a.exchange === b.exchange}
      filterOptions={(x) => x} // server-side filtering
      renderInput={(params) => (
        <TextField
          {...params}
          size="small"
          label={label}
          placeholder="Type symbol or name..."
          error={Boolean(error)}
          helperText={error ?? (q ? '' : recentOptions.length ? 'Recent' : '')}
          InputProps={{
            ...params.InputProps,
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
      )}
      renderOption={(propsEl, opt) => {
        const { key, ...liProps } = propsEl as any
        const title = `${opt.exchange}:${opt.symbol}`
        const secondaryParts: string[] = []
        if (opt.name) secondaryParts.push(opt.name)
        if (opt.tradingsymbol && opt.tradingsymbol !== opt.symbol) {
          secondaryParts.push(opt.tradingsymbol)
        }
        const secondary = secondaryParts.length
          ? secondaryParts.join(' - ')
          : opt.tradingsymbol
        return (
          <li key={key} {...liProps}>
            <ListItemText
              primary={<Typography variant="body2">{highlight(title, q)}</Typography>}
              secondary={
                secondary ? (
                  <Typography variant="caption" color="text.secondary">
                    {highlight(secondary, q)}
                  </Typography>
                ) : null
              }
            />
          </li>
        )
      }}
      sx={{ minWidth: 280 }}
    />
  )
}
