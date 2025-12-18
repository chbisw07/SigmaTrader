import Box from '@mui/material/Box'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Autocomplete from '@mui/material/Autocomplete'
import { alpha, useTheme } from '@mui/material/styles'
import { useEffect, useMemo, useState } from 'react'

import { listGroupMembers, listGroups, type Group } from '../services/groups'
import { fetchHoldings, type Holding } from '../services/positions'
import {
  fetchBasketIndices,
  fetchSymbolSeries,
  hydrateHistory,
  type BasketIndexResponse,
  type SymbolSeriesResponse,
} from '../services/dashboard'
import { PriceChart, type PriceChartType } from '../components/PriceChart'

type RangeOption = { value: any; label: string; helper?: string }

const RANGE_OPTIONS: RangeOption[] = [
  { value: '1d', label: '1D' },
  { value: '1w', label: '1W' },
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: '6m', label: '6M' },
  { value: 'ytd', label: 'YTD' },
  { value: '1y', label: '1Y' },
  { value: '2y', label: '2Y', helper: 'Max available' },
]

type ChartPoint = { x: number; y: number }

function parseDateMs(dateIso: string): number {
  // Treat date-only values as UTC midnight to keep the axis stable across TZs.
  return Date.parse(`${dateIso}T00:00:00Z`)
}

function formatDateLabel(ms: number, spanDays: number): string {
  const d = new Date(ms)
  if (spanDays <= 7) {
    return d.toLocaleDateString('en-IN', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
    })
  }
  if (spanDays <= 31) {
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
  }
  return d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}

function formatPct(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function formatAxisPct(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const rounded = Math.round(value)
  if (rounded === 0) return '0%'
  return `${rounded > 0 ? '+' : ''}${rounded}%`
}

function formatCompact(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e7) return `${(value / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `${(value / 1e5).toFixed(2)} L`
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)} K`
  return value.toFixed(2)
}

function MultiLineChart({
  series,
  height = 280,
  base = 100,
}: {
  series: Array<{
    label: string
    color: string
    points: ChartPoint[]
    coverage?: Record<number, { used: number; total: number }>
  }>
  height?: number
  base?: number
}) {
  const theme = useTheme()
  const [hoverX, setHoverX] = useState<number | null>(null)
  const width = 900
  const paddingLeft = 56
  const paddingRight = 20
  const paddingTop = 18
  const paddingBottom = 34
  const all = series.flatMap((s) => s.points)
  if (all.length < 2) {
    return (
      <Typography variant="body2" color="text.secondary">
        No chart data yet. Select Holdings/Groups and click Refresh.
      </Typography>
    )
  }

  const xs = all.map((p) => p.x)
  const ys = all.map((p) => p.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1

  const scaleX = (x: number) =>
    paddingLeft + ((x - minX) / spanX) * (width - paddingLeft - paddingRight)
  const scaleY = (y: number) =>
    height -
    paddingBottom -
    ((y - minY) / spanY) * (height - paddingTop - paddingBottom)

  const paths = series
    .map((s) => {
      const d = s.points
        .slice()
        .sort((a, b) => a.x - b.x)
        .map((p, i) => {
          const x = scaleX(p.x)
          const y = scaleY(p.y)
          return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
        })
        .join(' ')
      return { ...s, d }
    })
    .filter((p) => p.d.length > 0)

  const msPerDay = 24 * 60 * 60 * 1000
  const spanDays = Math.max(1, Math.round((maxX - minX) / msPerDay))

  const yTicks = 4
  const grid = Array.from({ length: yTicks + 1 }).map((_, i) => {
    const t = i / yTicks
    const y = paddingTop + t * (height - paddingTop - paddingBottom)
    const yValue = maxY - t * spanY
    const pct = ((yValue - base) / base) * 100
    return { y, yValue, pct }
  })

  const desiredXTicks = spanDays <= 7 ? 8 : spanDays <= 31 ? 6 : 6
  const uniqX = Array.from(new Set(all.map((p) => p.x))).sort((a, b) => a - b)
  const step = Math.max(1, Math.floor(uniqX.length / Math.max(2, desiredXTicks - 1)))
  const xTicks: number[] = []
  for (let i = 0; i < uniqX.length; i += step) xTicks.push(uniqX[i]!)
  if (xTicks[0] !== uniqX[0]) xTicks.unshift(uniqX[0]!)
  if (xTicks[xTicks.length - 1] !== uniqX[uniqX.length - 1]) xTicks.push(uniqX[uniqX.length - 1]!)
  const xTickLabels = xTicks.map((x) => formatDateLabel(x, spanDays))

  let hoverDateX: number | null = null
  if (hoverX != null && uniqX.length > 0) {
    // Binary search nearest x in uniqX.
    let lo = 0
    let hi = uniqX.length - 1
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2)
      if (uniqX[mid]! < hoverX) lo = mid + 1
      else hi = mid
    }
    const idx = lo
    const prev = idx > 0 ? idx - 1 : idx
    const a = uniqX[prev]!
    const b = uniqX[idx]!
    hoverDateX = Math.abs(a - hoverX) <= Math.abs(b - hoverX) ? a : b
  }

  const hoverSummary =
    hoverDateX == null
      ? null
      : {
          dateLabel: formatDateLabel(hoverDateX, spanDays),
          items: series.map((s) => {
            const point = s.points.find((p) => p.x === hoverDateX) ?? null
            const cov = s.coverage?.[hoverDateX] ?? null
            return { label: s.label, color: s.color, point, cov }
          }),
        }

  return (
    <Box sx={{ width: '100%', position: 'relative' }}>
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
      >
        {grid.map((g, idx) => (
          <line
            key={idx}
            x1={paddingLeft}
            x2={width - paddingRight}
            y1={g.y}
            y2={g.y}
            stroke={alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.18 : 0.12)}
            strokeWidth={1}
          />
        ))}
        {grid.map((g, idx) => (
          <text
            key={`yl_${idx}`}
            x={paddingLeft - 8}
            y={g.y + 4}
            textAnchor="end"
            fontSize={11}
            fill={alpha(theme.palette.text.secondary, 0.95)}
          >
            {formatAxisPct(g.pct)}
          </text>
        ))}
        {paths.map((p) => (
          <path
            key={p.label}
            d={p.d}
            fill="none"
            stroke={p.color}
            strokeWidth={2.5}
            strokeLinecap="round"
          />
        ))}
        {hoverDateX != null && (
          <>
            <line
              x1={scaleX(hoverDateX)}
              x2={scaleX(hoverDateX)}
              y1={paddingTop}
              y2={height - paddingBottom}
              stroke={alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.25 : 0.18)}
              strokeWidth={1}
            />
            {series.map((s) => {
              const p = s.points.find((pp) => pp.x === hoverDateX)
              if (!p) return null
              return (
                <circle
                  key={`dot_${s.label}`}
                  cx={scaleX(p.x)}
                  cy={scaleY(p.y)}
                  r={4}
                  fill={s.color}
                  stroke="#fff"
                  strokeWidth={2}
                />
              )
            })}
          </>
        )}
        <line
          x1={paddingLeft}
          x2={width - paddingRight}
          y1={height - paddingBottom}
          y2={height - paddingBottom}
          stroke={alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.18 : 0.12)}
          strokeWidth={1}
        />
        {xTicks.map((x, idx) => (
          <g key={`xt_${idx}`}>
            <line
              x1={scaleX(x)}
              x2={scaleX(x)}
              y1={height - paddingBottom}
              y2={height - paddingBottom + 4}
              stroke={alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.18 : 0.12)}
              strokeWidth={1}
            />
            <text
              x={scaleX(x)}
              y={height - 10}
              textAnchor={idx === 0 ? 'start' : idx === xTicks.length - 1 ? 'end' : 'middle'}
              fontSize={11}
              fill={alpha(theme.palette.text.secondary, 0.95)}
            >
              {xTickLabels[idx]}
            </text>
          </g>
        ))}
        <rect
          x={paddingLeft}
          y={paddingTop}
          width={width - paddingLeft - paddingRight}
          height={height - paddingTop - paddingBottom}
          fill="transparent"
          onMouseMove={(e) => {
            // `e` is an SVG event in React; compute viewBox x from clientX.
            const target = e.currentTarget as unknown as SVGRectElement
            const svg = target.ownerSVGElement
            if (!svg) return
            const rect = svg.getBoundingClientRect()
            const ratio = width / rect.width
            const xInView = (e.clientX - rect.left) * ratio
            const xValue =
              minX +
              ((xInView - paddingLeft) / (width - paddingLeft - paddingRight)) *
                spanX
            setHoverX(xValue)
          }}
          onMouseLeave={() => setHoverX(null)}
        />
      </svg>

      {hoverSummary && (
        <Paper
          elevation={0}
          variant="outlined"
          sx={{
            position: 'absolute',
            right: 12,
            top: 12,
            p: 1,
            minWidth: 220,
            bgcolor: alpha(theme.palette.background.paper, 0.96),
            backdropFilter: 'blur(6px)',
          }}
        >
          <Typography variant="subtitle2">{hoverSummary.dateLabel}</Typography>
          <Stack spacing={0.5} sx={{ mt: 0.5 }}>
            {hoverSummary.items.map((it) => {
              const y = it.point?.y
              const pct = y != null ? ((y - base) / base) * 100 : null
              return (
                <Box key={it.label} sx={{ display: 'flex', gap: 1, alignItems: 'baseline' }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: 99,
                      bgcolor: it.color,
                      mt: '2px',
                    }}
                  />
                  <Typography variant="body2" sx={{ flex: 1 }}>
                    {it.label}
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                    {y == null ? '—' : y.toFixed(2)}
                  </Typography>
                  {pct != null && (
                    <Typography
                      variant="caption"
                      color={pct >= 0 ? 'success.main' : 'error.main'}
                      sx={{ minWidth: 54, textAlign: 'right' }}
                    >
                      {formatPct(pct)}
                    </Typography>
                  )}
                </Box>
              )
            })}
            {hoverSummary.items.some((it) => it.cov) && (
              <Box sx={{ mt: 0.5 }}>
                {hoverSummary.items
                  .filter((it) => it.cov)
                  .map((it) => (
                    <Typography key={`cov_${it.label}`} variant="caption" color="text.secondary">
                      Coverage — {it.label}: {it.cov!.used}/{it.cov!.total}
                    </Typography>
                  ))}
              </Box>
            )}
          </Stack>
        </Paper>
      )}
    </Box>
  )
}

export function DashboardPage() {
  const [groups, setGroups] = useState<Group[]>([])
  const [loadingGroups, setLoadingGroups] = useState(false)
  const [groupsError, setGroupsError] = useState<string | null>(null)

  const [includeHoldings, setIncludeHoldings] = useState(true)
  const [selectedGroups, setSelectedGroups] = useState<Group[]>([])
  const [range, setRange] = useState<any>('6m')

  const [data, setData] = useState<BasketIndexResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [hydratingUniverse, setHydratingUniverse] = useState(false)
  const [hydrateError, setHydrateError] = useState<string | null>(null)

  type SymbolKey = { symbol: string; exchange: string; label: string }
  const [symbolOptions, setSymbolOptions] = useState<SymbolKey[]>([])
  const [loadingSymbols, setLoadingSymbols] = useState(false)
  const [symbolsError, setSymbolsError] = useState<string | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolKey | null>(null)

  const [symbolRange, setSymbolRange] = useState<any>('6m')
  const [chartType, setChartType] = useState<PriceChartType>('line')
  const [symbolData, setSymbolData] = useState<SymbolSeriesResponse | null>(null)
  const [loadingSymbolData, setLoadingSymbolData] = useState(false)
  const [symbolDataError, setSymbolDataError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoadingGroups(true)
        setGroupsError(null)
        const res = await listGroups()
        if (!active) return
        setGroups(res)
      } catch (err) {
        if (!active) return
        setGroupsError(err instanceof Error ? err.message : 'Failed to load groups')
      } finally {
        if (!active) return
        setLoadingGroups(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  const handleRefresh = async () => {
    const groupIds = selectedGroups.map((g) => g.id)
    if (!includeHoldings && groupIds.length === 0) {
      setError('Select Holdings and/or at least one group.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetchBasketIndices({
        include_holdings: includeHoldings,
        group_ids: groupIds,
        range,
        base: 100,
      } as any)
      setData(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to compute indices')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  const handleHydrateUniverse = async () => {
    const groupIds = selectedGroups.map((g) => g.id)
    if (!includeHoldings && groupIds.length === 0) return
    setHydratingUniverse(true)
    setHydrateError(null)
    try {
      const res = await hydrateHistory({
        include_holdings: includeHoldings,
        group_ids: groupIds,
        range,
        timeframe: '1d',
      } as any)
      if (res.failed > 0) {
        setHydrateError(
          `Hydration partially failed (${res.failed}). First error: ${res.errors?.[0] ?? 'Unknown error'}`,
        )
      }
      await handleRefresh()
    } catch (err) {
      setHydrateError(
        err instanceof Error ? err.message : 'Failed to hydrate universe history',
      )
    } finally {
      setHydratingUniverse(false)
    }
  }

  useEffect(() => {
    // Load something useful by default.
    void handleRefresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const palette = [
    '#2563eb',
    '#0f766e',
    '#7c3aed',
    '#f97316',
    '#dc2626',
    '#0891b2',
    '#16a34a',
  ]

  const chartSeries = useMemo(() => {
    const series = (data?.series ?? []).filter((s) => s.points.length > 0)
    return series.map((s, idx) => ({
      label: s.label,
      color: palette[idx % palette.length],
      points: s.points.map((p) => ({ x: parseDateMs(p.ts), y: p.value })),
      coverage: Object.fromEntries(
        s.points.map((p) => [
          parseDateMs(p.ts),
          { used: p.used_symbols, total: p.total_symbols },
        ]),
      ),
    }))
  }, [data])

  const summary = useMemo(() => {
    const series = (data?.series ?? []).filter((s) => s.points.length > 1)
    const items = series.map((s) => {
      const first = s.points[0]!
      const last = s.points[s.points.length - 1]!
      const ret = ((last.value - first.value) / first.value) * 100
      return { key: s.key, label: s.label, ret, last: last.value, missing: s.missing_symbols }
    })
    return items
  }, [data])

  const needsHydrateUniverse = useMemo(() => {
    return (data?.series ?? []).some((s) => (s.needs_hydrate_history_symbols ?? 0) > 0)
  }, [data])

  useEffect(() => {
    let active = true
    const loadSymbols = async () => {
      const groupIds = selectedGroups.map((g) => g.id)
      if (!includeHoldings && groupIds.length === 0) {
        setSymbolOptions([])
        setSelectedSymbol(null)
        return
      }
      setLoadingSymbols(true)
      setSymbolsError(null)
      try {
        const members: Array<{ symbol: string; exchange: string }> = []
        if (includeHoldings) {
          const holdings: Holding[] = await fetchHoldings()
          for (const h of holdings) {
            if (!h.symbol || !h.quantity || h.quantity <= 0) continue
            members.push({
              symbol: h.symbol.toUpperCase(),
              exchange: (h.exchange || 'NSE').toUpperCase(),
            })
          }
        }

        for (const g of selectedGroups) {
          const rows = await listGroupMembers(g.id)
          for (const r of rows) {
            if (!r.symbol) continue
            members.push({
              symbol: r.symbol.toUpperCase(),
              exchange: (r.exchange || 'NSE').toUpperCase(),
            })
          }
        }

        const uniq = new Map<string, SymbolKey>()
        for (const m of members) {
          const key = `${m.exchange}:${m.symbol}`
          if (uniq.has(key)) continue
          uniq.set(key, { symbol: m.symbol, exchange: m.exchange, label: key })
        }

        const options = Array.from(uniq.values()).sort((a, b) =>
          a.label.localeCompare(b.label),
        )
        if (!active) return
        setSymbolOptions(options)
        if (options.length === 0) {
          setSelectedSymbol(null)
        } else if (!selectedSymbol || !options.some((o) => o.label === selectedSymbol.label)) {
          setSelectedSymbol(options[0]!)
        }
      } catch (err) {
        if (!active) return
        setSymbolsError(err instanceof Error ? err.message : 'Failed to load symbols')
        setSymbolOptions([])
      } finally {
        if (!active) return
        setLoadingSymbols(false)
      }
    }

    void loadSymbols()
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeHoldings, selectedGroups])

  const loadSymbolSeries = async (hydrateMode: 'none' | 'auto' | 'force') => {
    if (!selectedSymbol) return
    setLoadingSymbolData(true)
    setSymbolDataError(null)
    try {
      const res = await fetchSymbolSeries({
        symbol: selectedSymbol.symbol,
        exchange: selectedSymbol.exchange,
        range: symbolRange,
        timeframe: '1d',
        hydrate_mode: hydrateMode,
      } as any)
      setSymbolData(res)
    } catch (err) {
      setSymbolData(null)
      setSymbolDataError(err instanceof Error ? err.message : 'Failed to load candles')
    } finally {
      setLoadingSymbolData(false)
    }
  }

  useEffect(() => {
    void loadSymbolSeries('auto')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol, symbolRange])

  const perf = useMemo(() => {
    const pts = symbolData?.points ?? []
    if (pts.length < 2) return null
    const closes = pts.map((p) => p.close)
    const last = closes[closes.length - 1]!
    const prev = closes[closes.length - 2]!
    const pct = (a: number, b: number) => (b === 0 ? 0 : ((a - b) / b) * 100)
    const at = (nBack: number) => {
      const idx = closes.length - 1 - nBack
      if (idx < 0) return null
      return pct(last, closes[idx]!)
    }
    return {
      today: pct(last, prev),
      d5: at(5),
      m1: at(21),
      m3: at(63),
      m6: at(126),
      y1: at(252),
      y2: at(504),
    }
  }, [symbolData])

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Dashboard
      </Typography>

      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', lg: 'row' },
          gap: 2,
        }}
      >
        <Paper variant="outlined" sx={{ p: 2, flex: 1, minWidth: 0 }}>
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={2} alignItems="center" sx={{ flexWrap: 'wrap' }}>
              <Typography variant="h6">Basket indices (base 100)</Typography>
              <Box sx={{ flex: 1 }} />
              {data && (
                <Typography variant="body2" color="text.secondary">
                  {data.start.slice(0, 10)} → {data.end.slice(0, 10)}
                </Typography>
              )}
            </Stack>

            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={2}
              alignItems={{ md: 'center' }}
            >
              <Autocomplete
                multiple
                options={groups}
                loading={loadingGroups}
                getOptionLabel={(g) => g.name}
                value={selectedGroups}
                onChange={(_e, value) => setSelectedGroups(value)}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Groups"
                    helperText={groupsError || 'Select groups to index (equal-weight).'}
                    error={!!groupsError}
                  />
                )}
                sx={{ flex: 1, minWidth: 320 }}
              />
              <Stack
                direction={{ xs: 'column', sm: 'row', md: 'row' }}
                spacing={1.5}
                alignItems={{ sm: 'center' }}
                sx={{ minWidth: { md: 420 } }}
              >
                <FormControlLabel
                  sx={{ mr: 0 }}
                  control={
                    <Checkbox
                      checked={includeHoldings}
                      onChange={(e) => setIncludeHoldings(e.target.checked)}
                    />
                  }
                  label="Include Holdings (Zerodha)"
                />
                <TextField
                  label="Range"
                  select
                  size="small"
                  value={range}
                  onChange={(e) => setRange(e.target.value as any)}
                  sx={{ minWidth: 120 }}
                >
                  {RANGE_OPTIONS.map((o) => (
                    <MenuItem key={o.value} value={o.value}>
                      {o.label}
                      {o.helper ? ` — ${o.helper}` : ''}
                    </MenuItem>
                  ))}
                </TextField>
                <Button
                  variant="contained"
                  onClick={handleRefresh}
                  disabled={loading}
                  sx={{ minWidth: 120 }}
                >
                  {loading ? 'Loading…' : 'Refresh'}
                </Button>
              </Stack>
            </Stack>

            {error && (
              <Typography variant="body2" color="error">
                {error}
              </Typography>
            )}

            {needsHydrateUniverse && (
              <Alert
                severity="warning"
                action={
                  <Button
                    color="inherit"
                    size="small"
                    onClick={handleHydrateUniverse}
                    disabled={hydratingUniverse}
                  >
                    {hydratingUniverse ? 'Hydrating…' : 'Hydrate universe'}
                  </Button>
                }
              >
                Missing history detected for this universe. Auto-hydrate only fills small recent
                gaps; hydrate the full universe to backfill larger history.
              </Alert>
            )}
            {hydrateError && (
              <Typography variant="body2" color="error">
                {hydrateError}
              </Typography>
            )}

            <Typography variant="caption" color="text.secondary">
              Auto-hydrate fills small recent gaps (last 30–60 days). Big history gaps require an
              explicit “Hydrate now” (from the Symbol explorer panel).
            </Typography>

            <Stack spacing={1}>
              {chartSeries.length > 0 && (
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} alignItems="center">
                  <Typography variant="caption" color="text.secondary">
                    Legend:
                  </Typography>
                  {chartSeries.map((s) => (
                    <Box
                      key={s.label}
                      sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mr: 1 }}
                    >
                      <Box
                        sx={{
                          width: 10,
                          height: 10,
                          borderRadius: 99,
                          bgcolor: s.color,
                        }}
                      />
                      <Typography variant="caption">{s.label}</Typography>
                    </Box>
                  ))}
                  <Box sx={{ flex: 1 }} />
                  <Typography variant="caption" color="text.secondary">
                    Hover for values + coverage
                  </Typography>
                </Stack>
              )}

              <MultiLineChart series={chartSeries} height={300} />

              {summary.length > 0 && (
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 1 }}>
                  {summary.map((s) => (
                    <Paper key={s.key} variant="outlined" sx={{ p: 1.5, minWidth: 220 }}>
                      <Typography variant="subtitle2">{s.label}</Typography>
                      <Typography variant="h6" sx={{ mt: 0.5 }}>
                        {formatCompact(s.last)}
                      </Typography>
                      <Typography
                        variant="body2"
                        color={s.ret >= 0 ? 'success.main' : 'error.main'}
                      >
                        {formatPct(s.ret)} (range)
                      </Typography>
                      {s.missing > 0 && (
                        <Typography variant="caption" color="text.secondary">
                          Missing symbols: {s.missing}
                        </Typography>
                      )}
                    </Paper>
                  ))}
                </Stack>
              )}
            </Stack>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, flex: 1, minWidth: 0 }}>
            <Stack spacing={1.5}>
              <Stack direction="row" spacing={2} alignItems="center">
                <Typography variant="h6">Symbol explorer</Typography>
                <Box sx={{ flex: 1 }} />
              </Stack>

              <Stack
                direction={{ xs: 'column', md: 'row' }}
                spacing={2}
                alignItems={{ md: 'center' }}
              >
                <Autocomplete
                  options={symbolOptions}
                  loading={loadingSymbols}
                  getOptionLabel={(o) => o.label}
                  value={selectedSymbol}
                  onChange={(_e, value) => setSelectedSymbol(value)}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Symbol"
                      helperText={symbolsError || 'Pick a symbol from the selected universe.'}
                      error={!!symbolsError}
                    />
                  )}
                  sx={{ flex: 1, minWidth: 260 }}
                />
                <Stack direction="row" spacing={1.5} alignItems="center">
                  <TextField
                    label="Range"
                    select
                    size="small"
                    value={symbolRange}
                    onChange={(e) => setSymbolRange(e.target.value as any)}
                    sx={{ minWidth: 120 }}
                  >
                    {RANGE_OPTIONS.map((o) => (
                      <MenuItem key={`sr_${o.value}`} value={o.value}>
                        {o.label}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Chart"
                    select
                    size="small"
                    value={chartType}
                    onChange={(e) => setChartType(e.target.value as PriceChartType)}
                    sx={{ minWidth: 120 }}
                  >
                    <MenuItem value="line">Line</MenuItem>
                    <MenuItem value="candles">Candles</MenuItem>
                  </TextField>
                </Stack>
              </Stack>

              {symbolData?.needs_hydrate_history && (
                <Alert
                  severity="warning"
                  action={
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => void loadSymbolSeries('force')}
                      disabled={loadingSymbolData}
                    >
                      {loadingSymbolData ? 'Hydrating…' : 'Hydrate now'}
                    </Button>
                  }
                >
                  Missing history for this range. Auto-hydrate only fills small recent gaps.
                </Alert>
              )}

              {symbolDataError && (
                <Typography variant="body2" color="error">
                  {symbolDataError}
                </Typography>
              )}

              {perf && (
                <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
                  <Typography variant="caption" color="text.secondary">
                    Perf:
                  </Typography>
                  <Typography variant="caption" color={perf.today >= 0 ? 'success.main' : 'error.main'}>
                    Today {formatPct(perf.today)}
                  </Typography>
                  {perf.d5 != null && (
                    <Typography variant="caption" color={perf.d5 >= 0 ? 'success.main' : 'error.main'}>
                      5D {formatPct(perf.d5)}
                    </Typography>
                  )}
                  {perf.m1 != null && (
                    <Typography variant="caption" color={perf.m1 >= 0 ? 'success.main' : 'error.main'}>
                      1M {formatPct(perf.m1)}
                    </Typography>
                  )}
                  {perf.m3 != null && (
                    <Typography variant="caption" color={perf.m3 >= 0 ? 'success.main' : 'error.main'}>
                      3M {formatPct(perf.m3)}
                    </Typography>
                  )}
                  {perf.m6 != null && (
                    <Typography variant="caption" color={perf.m6 >= 0 ? 'success.main' : 'error.main'}>
                      6M {formatPct(perf.m6)}
                    </Typography>
                  )}
                  {perf.y1 != null && (
                    <Typography variant="caption" color={perf.y1 >= 0 ? 'success.main' : 'error.main'}>
                      1Y {formatPct(perf.y1)}
                    </Typography>
                  )}
                  {perf.y2 != null && (
                    <Typography variant="caption" color={perf.y2 >= 0 ? 'success.main' : 'error.main'}>
                      2Y {formatPct(perf.y2)}
                    </Typography>
                  )}
                </Stack>
              )}

              <PriceChart
                candles={symbolData?.points ?? []}
                chartType={chartType}
                height={340}
              />

              {symbolData && (
                <Typography variant="caption" color="text.secondary">
                  Coverage — head gap: {symbolData.head_gap_days}d, tail gap:{' '}
                  {symbolData.tail_gap_days}d
                </Typography>
              )}
            </Stack>
          </Paper>
      </Box>
    </Box>
  )
}
