import Box from '@mui/material/Box'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Autocomplete from '@mui/material/Autocomplete'
import { alpha, useTheme } from '@mui/material/styles'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'
import { listGroups, type Group } from '../services/groups'
import { fetchBrokerCapabilities } from '../services/brokerRuntime'
import { fetchZerodhaStatus } from '../services/zerodha'
import { fetchAngeloneStatus } from '../services/angelone'
import {
  fetchBasketIndices,
  fetchSymbolSeries,
  hydrateHistory,
  type BasketIndexResponse,
  type SymbolSeriesResponse,
} from '../services/dashboard'
import { HoldingsSummaryHistoryPanel } from '../components/HoldingsSummaryHistoryPanel'
import { normalizeMarketSymbols, searchMarketSymbols, type MarketSymbol } from '../services/marketData'

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

const INDICES_CACHE_KEY = 'st_dashboard_indices_cache_v1'
const DASHBOARD_SETTINGS_KEY = 'st_dashboard_settings_v1'

type DashboardSettingsV1 = {
  includeHoldings?: boolean
  holdingsBrokers?: string[]
  groupIds?: number[]
  range?: string
  symbolRange?: string
  // Legacy global display mode (kept for backwards compatibility/migration).
  chartDisplayMode?: 'value' | 'pct'
  // Per-chart display modes.
  indicesChartDisplayMode?: 'value' | 'pct'
  // Symbol compare display mode: base100 ("value") or % return ("pct").
  symbolChartDisplayMode?: 'value' | 'pct'
  holdingsHistoryChartDisplayMode?: 'value' | 'pct'
  selectedSymbol?: { symbol: string; exchange: string; name?: string | null } | null
  benchmarks?: Array<{ symbol: string; exchange: string; name?: string | null }>
}

function loadDashboardSettings(): DashboardSettingsV1 {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(DASHBOARD_SETTINGS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as DashboardSettingsV1
    if (!parsed || typeof parsed !== 'object') return {}
    return parsed
  } catch {
    return {}
  }
}

function saveDashboardSettings(next: DashboardSettingsV1): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(DASHBOARD_SETTINGS_KEY, JSON.stringify(next))
  } catch {
    // ignore persistence errors
  }
}

function MultiLineChart({
  series,
  height = 280,
  base = 100,
  displayMode = 'value',
  emptyText,
}: {
  series: Array<{
    label: string
    color: string
    points: ChartPoint[]
    coverage?: Record<number, { used: number; total: number }>
  }>
  height?: number
  base?: number
  displayMode?: 'value' | 'pct'
  emptyText?: string
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
        {emptyText ?? 'No chart data yet.'}
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
            {displayMode === 'pct' ? formatAxisPct(g.pct) : formatCompact(g.yValue)}
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
                    {y == null
                      ? '—'
                      : displayMode === 'pct'
                        ? formatPct(((y - base) / base) * 100)
                        : y.toFixed(2)}
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
  const { displayTimeZone } = useTimeSettings()
  const [initialSettings] = useState<DashboardSettingsV1>(() =>
    loadDashboardSettings(),
  )
  const persistedGroupIdsRef = useRef<number[]>(
    Array.isArray(initialSettings.groupIds)
      ? initialSettings.groupIds.filter((x) => typeof x === 'number')
      : [],
  )
  const indicesInitDoneRef = useRef(false)

  const [groups, setGroups] = useState<Group[]>([])
  const [loadingGroups, setLoadingGroups] = useState(false)
  const [groupsError, setGroupsError] = useState<string | null>(null)

  const [includeHoldings, setIncludeHoldings] = useState(() =>
    typeof initialSettings.includeHoldings === 'boolean'
      ? initialSettings.includeHoldings
      : true,
  )
  const [holdingsBrokers, setHoldingsBrokers] = useState<string[]>(() => {
    const raw = initialSettings.holdingsBrokers
    if (Array.isArray(raw)) {
      return raw.filter((x) => typeof x === 'string' && x.trim()).map((x) => x.trim())
    }
    return []
  })
  const [brokerOptions, setBrokerOptions] = useState<Array<{ name: string; label: string }>>(
    [],
  )
  const [connectedBrokers, setConnectedBrokers] = useState<Record<string, boolean>>({})
  const [selectedGroups, setSelectedGroups] = useState<Group[]>([])
  const [range, setRange] = useState<any>(() => initialSettings.range ?? '6m')

	  const [data, setData] = useState<BasketIndexResponse | null>(null)
	  const [loading, setLoading] = useState(false)
	  const [error, setError] = useState<string | null>(null)
	  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null)

  const [hydratingUniverse, setHydratingUniverse] = useState(false)
  const [hydrateError, setHydrateError] = useState<string | null>(null)

  const [symbolQuery, setSymbolQuery] = useState<string>('')
  const [symbolOptions, setSymbolOptions] = useState<MarketSymbol[]>([])
  const [loadingSymbols, setLoadingSymbols] = useState(false)
  const [symbolsError, setSymbolsError] = useState<string | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<MarketSymbol | null>(() => {
    const s = initialSettings.selectedSymbol as any
    if (!s || typeof s !== 'object') return null
    const symbol = String(s.symbol ?? '').trim().toUpperCase()
    const exchange = String(s.exchange ?? '').trim().toUpperCase()
    const name = s.name != null ? String(s.name) : null
    if (!symbol || !exchange) return null
    return { symbol, exchange, name }
  })

  const [benchmarkQuery, setBenchmarkQuery] = useState<string>('')
  const [benchmarkOptions, setBenchmarkOptions] = useState<MarketSymbol[]>([])
  const [loadingBenchmarks, setLoadingBenchmarks] = useState(false)
  const [benchmarksError, setBenchmarksError] = useState<string | null>(null)
  const [benchmarks, setBenchmarks] = useState<MarketSymbol[]>(() => {
    const raw = (initialSettings.benchmarks ?? []) as any
    if (!Array.isArray(raw)) return []
    const out: MarketSymbol[] = []
    for (const it of raw) {
      if (!it || typeof it !== 'object') continue
      const symbol = String(it.symbol ?? '').trim().toUpperCase()
      const exchange = String(it.exchange ?? '').trim().toUpperCase()
      const name = it.name != null ? String(it.name) : null
      if (!symbol || !exchange) continue
      out.push({ symbol, exchange, name })
    }
    return out
  })

  const [symbolRange, setSymbolRange] = useState<any>(
    () => initialSettings.symbolRange ?? '6m',
  )
  const initialDisplayMode: 'value' | 'pct' = initialSettings.chartDisplayMode ?? 'value'
  const [indicesChartDisplayMode, setIndicesChartDisplayMode] = useState<'value' | 'pct'>(
    () => initialSettings.indicesChartDisplayMode ?? initialDisplayMode,
  )
  const [symbolChartDisplayMode, setSymbolChartDisplayMode] = useState<'value' | 'pct'>(
    () => initialSettings.symbolChartDisplayMode ?? initialDisplayMode,
  )
  const [holdingsHistoryChartDisplayMode, setHoldingsHistoryChartDisplayMode] = useState<
    'value' | 'pct'
  >(() => initialSettings.holdingsHistoryChartDisplayMode ?? initialDisplayMode)
  const [seriesByKey, setSeriesByKey] = useState<Record<string, SymbolSeriesResponse>>({})
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

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const caps = await fetchBrokerCapabilities()
        if (!active) return
        setBrokerOptions(caps.map((c) => ({ name: c.name, label: c.label })))
      } catch {
        if (!active) return
        setBrokerOptions([
          { name: 'zerodha', label: 'Zerodha (Kite)' },
          { name: 'angelone', label: 'AngelOne (SmartAPI)' },
        ])
      }

      try {
        const [z, a] = await Promise.allSettled([fetchZerodhaStatus(), fetchAngeloneStatus()])
        if (!active) return
        setConnectedBrokers({
          zerodha: z.status === 'fulfilled' ? Boolean(z.value.connected) : false,
          angelone: a.status === 'fulfilled' ? Boolean(a.value.connected) : false,
        })
      } catch {
        if (!active) return
        setConnectedBrokers({})
      }
    })()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!includeHoldings) return
    if (holdingsBrokers.length > 0) return
    const connected = Object.entries(connectedBrokers)
      .filter(([, ok]) => ok)
      .map(([name]) => name)
    if (connected.length > 0) {
      setHoldingsBrokers(connected)
    } else {
      setHoldingsBrokers(['zerodha'])
    }
  }, [connectedBrokers, holdingsBrokers.length, includeHoldings])

  const [settingsHydrated, setSettingsHydrated] = useState(false)
  useEffect(() => {
    if (settingsHydrated) return
    if (!groups.length) return
    if (selectedGroups.length) {
      setSettingsHydrated(true)
      return
    }
    const ids = persistedGroupIdsRef.current
    if (!ids.length) {
      setSettingsHydrated(true)
      return
    }
    const byId = new Map(groups.map((g) => [g.id, g] as const))
    const next = ids
      .map((id) => byId.get(id))
      .filter((g): g is Group => !!g)
    if (next.length) setSelectedGroups(next)
    setSettingsHydrated(true)
  }, [groups, selectedGroups.length, settingsHydrated])
	  const handleRefresh = async () => {
	    const groupIds = selectedGroups.map((g) => g.id)
	    if (!includeHoldings && groupIds.length === 0) {
	      setError('Select Holdings and/or at least one group.')
	      return
    }
    setLoading(true)
	    setError(null)
	    try {
	      const sortedGroupIds = [...groupIds].sort((a, b) => a - b)
        const sortedHoldingsBrokers = [...holdingsBrokers]
          .map((b) => b.trim().toLowerCase())
          .filter(Boolean)
          .sort()
	      const res = await fetchBasketIndices({
	        include_holdings: includeHoldings,
          holdings_brokers: includeHoldings ? sortedHoldingsBrokers : [],
	        group_ids: sortedGroupIds,
	        range,
	        base: 100,
	      } as any)
	      setData(res)
	      const refreshedAt = new Date().toISOString()
	      setLastRefreshedAt(refreshedAt)
	      if (typeof window !== 'undefined') {
	        try {
	          const cache = {
	            config: {
	              include_holdings: includeHoldings,
                holdings_brokers: sortedHoldingsBrokers,
	              range,
	              group_ids: sortedGroupIds,
	            },
	            response: res,
	            refreshed_at: refreshedAt,
	          }
	          window.localStorage.setItem(INDICES_CACHE_KEY, JSON.stringify(cache))
	        } catch {
	          // ignore cache errors
	        }
	      }
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
      const sortedHoldingsBrokers = [...holdingsBrokers]
        .map((b) => b.trim().toLowerCase())
        .filter(Boolean)
        .sort()
      const res = await hydrateHistory({
        include_holdings: includeHoldings,
        holdings_brokers: includeHoldings ? sortedHoldingsBrokers : [],
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
      if (indicesInitDoneRef.current) return

      const hasPersistedGroups = persistedGroupIdsRef.current.length > 0
      // If we have persisted groups, wait until we hydrate them; otherwise we
      // might run with an empty group selection and miss cache hits.
      if (hasPersistedGroups && !settingsHydrated) return

      const groupIds = selectedGroups.map((g) => g.id)
      if (!includeHoldings && groupIds.length === 0) return

	    const init = async () => {
	      const sortedGroupIds = [...groupIds].sort((a, b) => a - b)
        const sortedHoldingsBrokers = [...holdingsBrokers]
          .map((b) => b.trim().toLowerCase())
          .filter(Boolean)
          .sort()
	      if (typeof window !== 'undefined') {
	        try {
	          const raw = window.localStorage.getItem(INDICES_CACHE_KEY)
	          if (raw) {
	            const parsed = JSON.parse(raw) as {
	              config?: {
                  include_holdings?: boolean
                  holdings_brokers?: string[]
                  range?: any
                  group_ids?: number[]
                }
	              response?: BasketIndexResponse
	              refreshed_at?: string
	            }
	            const cfg = parsed.config
	            if (
	              cfg &&
	              typeof cfg.include_holdings === 'boolean' &&
	              cfg.range === range &&
	              Array.isArray(cfg.group_ids)
	            ) {
	              const cachedIds = cfg.group_ids.slice().sort((a, b) => a - b)
                const cachedBrokers = Array.isArray(cfg.holdings_brokers)
                  ? cfg.holdings_brokers.slice().map((b) => String(b)).sort()
                  : []
                const sameBrokers =
                  cachedBrokers.length === sortedHoldingsBrokers.length &&
                  cachedBrokers.every((v, idx) => v === sortedHoldingsBrokers[idx])
	              const sameLength = cachedIds.length === sortedGroupIds.length
	              const sameIds =
	                sameLength &&
	                cachedIds.every((v, idx) => v === sortedGroupIds[idx])
	              if (
                  sameIds &&
                  cfg.include_holdings === includeHoldings &&
                  sameBrokers &&
                  parsed.response
                ) {
	                setData(parsed.response)
	                setLastRefreshedAt(parsed.refreshed_at ?? null)
	                return
	              }
	            }
	          }
	        } catch {
	          // ignore cache errors
	        }
	      }
	      await handleRefresh()
	    }
	    void init()
      indicesInitDoneRef.current = true
	  }, [includeHoldings, holdingsBrokers, range, selectedGroups, settingsHydrated])

  useEffect(() => {
    const groupIds =
      selectedGroups.length > 0
        ? selectedGroups.map((g) => g.id)
        : settingsHydrated
          ? []
          : persistedGroupIdsRef.current

    persistedGroupIdsRef.current = groupIds

	    saveDashboardSettings({
	      includeHoldings,
	      holdingsBrokers,
	      groupIds,
	      range: String(range ?? ''),
	      symbolRange: String(symbolRange ?? ''),
	        indicesChartDisplayMode,
	        symbolChartDisplayMode,
	        holdingsHistoryChartDisplayMode,
	      selectedSymbol,
        benchmarks,
	    })
	  }, [
	    includeHoldings,
	    indicesChartDisplayMode,
	    holdingsHistoryChartDisplayMode,
	    holdingsBrokers,
	    range,
	    selectedGroups,
	    selectedSymbol,
	    symbolChartDisplayMode,
	    settingsHydrated,
        benchmarks,
	    symbolRange,
	  ])

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

  const instrumentKey = (s: { symbol: string; exchange: string }) =>
    `${String(s.exchange || 'NSE').toUpperCase()}:${String(s.symbol || '').toUpperCase()}`

  const formatInstrumentLabel = (s: MarketSymbol): string => {
    const sym = String(s.symbol || '').trim().toUpperCase()
    const exch = String(s.exchange || '').trim().toUpperCase()
    return exch ? `${exch}:${sym}` : sym
  }

  const toDateOnly = (ts: string): string => {
    const t = String(ts || '')
    const idx = t.indexOf('T')
    return idx >= 0 ? t.slice(0, idx) : t.slice(0, 10)
  }

  useEffect(() => {
    let active = true
    const q = symbolQuery.trim()
    if (!q) {
      setSymbolOptions([])
      setSymbolsError(null)
      setLoadingSymbols(false)
      return
    }
    const t = window.setTimeout(async () => {
      setLoadingSymbols(true)
      setSymbolsError(null)
      try {
        const res = await searchMarketSymbols({ q, limit: 30 })
        if (!active) return
        setSymbolOptions(res)
      } catch (err) {
        if (!active) return
        setSymbolsError(err instanceof Error ? err.message : 'Failed to search symbols')
        setSymbolOptions([])
      } finally {
        if (!active) return
        setLoadingSymbols(false)
      }
    }, 250)
    return () => {
      active = false
      window.clearTimeout(t)
    }
  }, [symbolQuery])

  useEffect(() => {
    let active = true
    const q = benchmarkQuery.trim()
    if (!q) {
      setBenchmarkOptions([])
      setBenchmarksError(null)
      setLoadingBenchmarks(false)
      return
    }
    const t = window.setTimeout(async () => {
      setLoadingBenchmarks(true)
      setBenchmarksError(null)
      try {
        const res = await searchMarketSymbols({ q, limit: 30 })
        if (!active) return
        setBenchmarkOptions(res)
      } catch (err) {
        if (!active) return
        setBenchmarksError(err instanceof Error ? err.message : 'Failed to search symbols')
        setBenchmarkOptions([])
      } finally {
        if (!active) return
        setLoadingBenchmarks(false)
      }
    }, 250)
    return () => {
      active = false
      window.clearTimeout(t)
    }
  }, [benchmarkQuery])

  useEffect(() => {
    if (benchmarks.length > 0) return
    let active = true
    void (async () => {
      try {
        const candidates = [
          'NSE:NIFTY 50',
          'NSE:NIFTY50',
          'NSE:NIFTY',
          'NSE:NIFTYBEES',
        ]
        const res = await normalizeMarketSymbols({
          items: candidates,
          default_exchange: 'NSE',
        })
        if (!active) return
        const firstValid = (res.items ?? []).find((x) => x.valid)
        if (!firstValid?.normalized_symbol || !firstValid.normalized_exchange) {
          setBenchmarksError('Default benchmark not found (tried NIFTY50/NIFTYBEES).')
          return
        }
        setBenchmarks([
          {
            symbol: firstValid.normalized_symbol,
            exchange: firstValid.normalized_exchange,
            name: null,
          },
        ])
      } catch (err) {
        if (!active) return
        setBenchmarksError(
          err instanceof Error ? err.message : 'Failed to set default benchmark',
        )
      }
    })()
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [benchmarks.length])

  useEffect(() => {
    const selfKey = selectedSymbol ? instrumentKey(selectedSymbol) : null
    setBenchmarks((prev) => {
      const out: MarketSymbol[] = []
      const seen = new Set<string>()
      for (const s of prev) {
        const key = instrumentKey(s)
        if (selfKey && key === selfKey) continue
        if (seen.has(key)) continue
        seen.add(key)
        out.push({ symbol: s.symbol, exchange: s.exchange, name: s.name ?? null })
        if (out.length >= 5) break
      }
      return out
    })
  }, [selectedSymbol?.symbol, selectedSymbol?.exchange])

  const loadCompareSeries = async (hydrateMode: 'none' | 'auto' | 'force') => {
    if (!selectedSymbol) {
      setSeriesByKey({})
      return
    }
    const instruments = [selectedSymbol, ...benchmarks]
    const uniq: MarketSymbol[] = []
    const seen = new Set<string>()
    for (const s of instruments) {
      const key = instrumentKey(s)
      if (seen.has(key)) continue
      seen.add(key)
      uniq.push(s)
    }

    setLoadingSymbolData(true)
    setSymbolDataError(null)
    try {
      const results = await Promise.allSettled(
        uniq.map((s) =>
          fetchSymbolSeries({
            symbol: s.symbol,
            exchange: s.exchange,
            range: symbolRange,
            timeframe: '1d',
            hydrate_mode: hydrateMode,
          } as any),
        ),
      )
      const next: Record<string, SymbolSeriesResponse> = {}
      let firstErr: string | null = null
      results.forEach((res, idx) => {
        const s = uniq[idx]!
        const key = instrumentKey(s)
        if (res.status === 'fulfilled') {
          next[key] = res.value
        } else if (!firstErr) {
          firstErr =
            res.reason instanceof Error ? res.reason.message : 'Failed to load series'
        }
      })
      setSeriesByKey(next)
      if (firstErr) setSymbolDataError(firstErr)
    } finally {
      setLoadingSymbolData(false)
    }
  }

  const compareKey = useMemo(() => {
    const keys = [
      selectedSymbol ? instrumentKey(selectedSymbol) : '',
      ...benchmarks.map(instrumentKey),
      String(symbolRange ?? ''),
    ].filter(Boolean)
    return keys.join('|')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol?.symbol, selectedSymbol?.exchange, benchmarks, symbolRange])

  useEffect(() => {
    void loadCompareSeries('auto')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compareKey])

  const compareChartSeries = useMemo(() => {
    if (!selectedSymbol) return []
    const instruments = [selectedSymbol, ...benchmarks]
    const present: Array<{ ref: MarketSymbol; data: SymbolSeriesResponse }> = []
    const seen = new Set<string>()
    for (const s of instruments) {
      const key = instrumentKey(s)
      if (seen.has(key)) continue
      seen.add(key)
      const data = seriesByKey[key]
      if (!data || (data.points ?? []).length < 2) continue
      present.push({ ref: s, data })
    }
    if (present.length === 0) return []

    const starts = present
      .map((p) => toDateOnly((p.data.points ?? [])[0]?.ts ?? ''))
      .filter(Boolean)
    const commonStart = starts.reduce((acc, cur) => (acc < cur ? cur : acc), starts[0]!)

    return present.map((p, idx) => {
      const pts = (p.data.points ?? [])
        .map((x) => ({ ts: toDateOnly(x.ts), close: x.close }))
        .filter((x) => x.ts && Number.isFinite(x.close) && x.ts >= commonStart)
        .sort((a, b) => a.ts.localeCompare(b.ts))
      const baseClose = pts[0]?.close ?? 0
      const points =
        baseClose > 0
          ? pts.map((x) => ({ x: parseDateMs(x.ts), y: (x.close / baseClose) * 100 }))
          : []
      return {
        label: formatInstrumentLabel(p.ref),
        color: palette[idx % palette.length]!,
        points,
      }
    })
  }, [benchmarks, palette, selectedSymbol, seriesByKey])

  const compareSummary = useMemo(() => {
    return compareChartSeries
      .map((s) => {
        const pts = s.points ?? []
        if (pts.length < 2) return null
        const first = pts[0]!.y
        const last = pts[pts.length - 1]!.y
        const ret = first === 0 ? 0 : ((last - first) / first) * 100
        return { label: s.label, color: s.color, ret }
      })
      .filter(Boolean) as Array<{ label: string; color: string; ret: number }>
  }, [compareChartSeries])

  const needsHydrateSymbols = useMemo(() => {
    return Object.values(seriesByKey).some((s) => Boolean(s?.needs_hydrate_history))
  }, [seriesByKey])

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2, flexWrap: 'wrap' }}>
        <Typography variant="h4">Dashboard</Typography>
        <Box sx={{ flex: 1 }} />
      </Stack>

      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', lg: 'row' },
          gap: 2,
        }}
      >
        <Paper
          variant="outlined"
          sx={{ p: 2, flexGrow: { xs: 1, lg: 1 }, flexBasis: 0, minWidth: 0 }}
        >
          <Stack spacing={1.5}>
	            <Stack direction="row" spacing={2} alignItems="center" sx={{ flexWrap: 'wrap' }}>
	              <Typography variant="h6">Basket indices (base 100)</Typography>
	              <Box sx={{ flex: 1 }} />
	              {data && (
	                <Typography variant="body2" color="text.secondary">
	                  {data.start.slice(0, 10)} → {data.end.slice(0, 10)}
	                </Typography>
	              )}
		              {lastRefreshedAt && (
		                <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
		                  Last refreshed: {formatInDisplayTimeZone(lastRefreshedAt, displayTimeZone)}
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
                  label="Include Holdings"
                />
                {includeHoldings && (
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
                    {(brokerOptions.length ? brokerOptions : [
                      { name: 'zerodha', label: 'Zerodha (Kite)' },
                      { name: 'angelone', label: 'AngelOne (SmartAPI)' },
                    ])
                      .filter((b) => {
                        const ok = connectedBrokers[b.name]
                        return ok == null ? true : ok
                      })
                      .map((b) => {
                        const checked = holdingsBrokers.includes(b.name)
                        const disableUncheckLast = checked && holdingsBrokers.length <= 1
                        const shortLabel = b.name === 'zerodha' ? 'Zerodha' : b.name === 'angelone' ? 'AngelOne' : b.label
                        return (
                          <FormControlLabel
                            key={`holdings_${b.name}`}
                            sx={{ mr: 0 }}
                            control={
                              <Checkbox
                                size="small"
                                checked={checked}
                                disabled={disableUncheckLast}
                                onChange={(e) => {
                                  const nextChecked = e.target.checked
                                  setHoldingsBrokers((prev) => {
                                    const norm = b.name.trim().toLowerCase()
                                    const set = new Set(prev.map((x) => x.trim().toLowerCase()).filter(Boolean))
                                    if (nextChecked) set.add(norm)
                                    else set.delete(norm)
                                    const out = Array.from(set)
                                    return out.length ? out : prev
                                  })
                                }}
                              />
                            }
                            label={shortLabel}
                          />
                        )
                      })}
                  </Stack>
                )}
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
                <TextField
                  label="Display"
                  select
                  size="small"
                  value={indicesChartDisplayMode}
                  onChange={(e) =>
                    setIndicesChartDisplayMode(e.target.value === 'pct' ? 'pct' : 'value')
                  }
                  sx={{ minWidth: 120 }}
                >
                  <MenuItem value="value">Value</MenuItem>
                  <MenuItem value="pct">%</MenuItem>
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

              <MultiLineChart
                series={chartSeries}
                height={300}
                displayMode={indicesChartDisplayMode}
                emptyText="No chart data yet. Select Holdings/Groups and click Refresh."
              />

              {summary.length > 0 && (
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 1 }}>
                  {summary.map((s) => (
                    <Paper key={s.key} variant="outlined" sx={{ p: 1.5, minWidth: 220 }}>
                      <Typography variant="subtitle2">{s.label}</Typography>
                      <Typography variant="h6" sx={{ mt: 0.5 }}>
                        {indicesChartDisplayMode === 'pct'
                          ? formatPct(s.ret)
                          : formatCompact(s.last)}
                      </Typography>
                      {indicesChartDisplayMode === 'value' && (
                        <Typography
                          variant="body2"
                          color={s.ret >= 0 ? 'success.main' : 'error.main'}
                        >
                          {formatPct(s.ret)} (range)
                        </Typography>
                      )}
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

        <Paper
          variant="outlined"
          sx={{ p: 2, flexGrow: { xs: 1, lg: 1 }, flexBasis: 0, minWidth: 0 }}
        >
            <Stack spacing={1.5}>
              <Stack direction="row" spacing={2} alignItems="center">
                <Typography variant="h6">Symbol compare</Typography>
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
                  value={selectedSymbol}
                  onChange={(_e, v) => setSelectedSymbol(v)}
                  onInputChange={(_e, v) => setSymbolQuery(v.toUpperCase())}
                  getOptionLabel={(o) => `${o.symbol} (${o.exchange})`}
                  isOptionEqualToValue={(a, b) => a.symbol === b.symbol && a.exchange === b.exchange}
                  renderOption={(props, option) => (
                    <li {...props}>
                      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                        <Typography variant="body2">
                          {option.symbol} ({option.exchange})
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
                      label="Symbol"
                      helperText={symbolsError ?? 'Start typing to search symbols (stocks/ETFs/indices).'}
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
                    label="Display"
                    select
                    size="small"
                    value={symbolChartDisplayMode}
                    onChange={(e) =>
                      setSymbolChartDisplayMode(e.target.value === 'pct' ? 'pct' : 'value')
                    }
                    sx={{ minWidth: 120 }}
                  >
                    <MenuItem value="value">Base 100</MenuItem>
                    <MenuItem value="pct">%</MenuItem>
                  </TextField>
                </Stack>
              </Stack>

              {needsHydrateSymbols && (
                <Alert
                  severity="warning"
                  action={
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => void loadCompareSeries('force')}
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

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  Benchmarks (max 5)
                </Typography>
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{ flexWrap: 'wrap', alignItems: 'center' }}
                >
                  {benchmarks.map((b) => (
                    <Chip
                      key={formatInstrumentLabel(b)}
                      label={formatInstrumentLabel(b)}
                      size="small"
                      onDelete={() => {
                        const key = formatInstrumentLabel(b)
                        setBenchmarks((prev) =>
                          prev.filter((x) => formatInstrumentLabel(x) !== key),
                        )
                      }}
                    />
                  ))}
                  {benchmarks.length < 5 && (
                    <Autocomplete
                      options={benchmarkOptions}
                      loading={loadingBenchmarks}
                      value={null}
                      onChange={(_e, v) => {
                        if (!v) return
                        setBenchmarksError(null)
                        setBenchmarks((prev) => {
                          if (prev.length >= 5) {
                            setBenchmarksError('Max 5 benchmarks.')
                            return prev
                          }
                          const key = formatInstrumentLabel(v)
                          if (prev.some((x) => formatInstrumentLabel(x) === key)) return prev
                          return [...prev, v]
                        })
                        setBenchmarkQuery('')
                        setBenchmarkOptions([])
                      }}
                      onInputChange={(_e, v) => setBenchmarkQuery(v.toUpperCase())}
                      getOptionLabel={(o) => `${o.symbol} (${o.exchange})`}
                      isOptionEqualToValue={(a, b) =>
                        a.symbol === b.symbol && a.exchange === b.exchange
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="Add benchmark"
                          size="small"
                          sx={{ minWidth: 240 }}
                        />
                      )}
                      sx={{ minWidth: 240 }}
                    />
                  )}
                </Stack>
                {benchmarksError && (
                  <Typography variant="caption" color="error">
                    {benchmarksError}
                  </Typography>
                )}
              </Box>

              {compareSummary.length > 0 && (
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={1.5}
                  sx={{ flexWrap: 'wrap' }}
                >
                  {compareSummary.map((s) => (
                    <Paper key={s.label} variant="outlined" sx={{ p: 1.25, minWidth: 220 }}>
                      <Typography variant="subtitle2">{s.label}</Typography>
                      <Typography
                        variant="h6"
                        sx={{ mt: 0.5 }}
                        color={s.ret >= 0 ? 'success.main' : 'error.main'}
                      >
                        {formatPct(s.ret)}
                      </Typography>
                    </Paper>
                  ))}
                </Stack>
              )}

              <MultiLineChart
                series={compareChartSeries}
                height={340}
                base={100}
                displayMode={symbolChartDisplayMode}
                emptyText="No chart data yet. Pick a symbol to compare."
              />

              {/*
              <Accordion disableGutters defaultExpanded={false}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">Indicators</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() =>
                          setIndicatorRows((prev) => [
                            ...prev,
                            { name: '', kind: 'SMA', params: { source: 'close', length: 20, timeframe: '1d' }, enabled: true, plot: 'price' },
                          ])
                        }
                      >
                        Add indicator
                      </Button>
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() => void applyIndicators()}
                        disabled={indicatorLoading || enabledVariables.length === 0}
                      >
                        {indicatorLoading ? 'Applying…' : 'Apply'}
                      </Button>
                      <Tooltip title="Refresh custom indicators">
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => void refreshCustomIndicators()}
                            disabled={customIndicatorsLoading}
                          >
                            <RefreshIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Button
                        size="small"
                        variant="text"
                        onClick={() =>
                          window.open('/alerts?tab=indicators', '_blank', 'noopener,noreferrer')
                        }
                      >
                        Add new indicator
                      </Button>
                      <Box sx={{ flex: 1 }} />
                      <Button
                        size="small"
                        color="error"
                        onClick={() => {
                          setIndicatorRows([])
                          setIndicatorData(null)
                        }}
                      >
                        Clear
                      </Button>
                    </Stack>

                    {customIndicatorsError && (
                      <Typography variant="caption" color="error">
                        {customIndicatorsError}
                      </Typography>
                    )}
                    {indicatorError && (
                      <Typography variant="caption" color="error">
                        {indicatorError}
                      </Typography>
                    )}

                    <Stack spacing={1}>
                      {indicatorRows.map((row, idx) => {
                        const params = (row.params ?? {}) as Record<string, any>
                        const kind = String(row.kind || 'SMA').toUpperCase()
                        const swatchColor =
                          chartOverlays.find(
                            (o) => o.name.toUpperCase() === String(row.name || '').trim().toUpperCase(),
                          )?.color ?? null
                        const needsSourceOrPrice = ['SMA', 'EMA', 'RSI', 'STDDEV', 'RET', 'OBV', 'VWAP'].includes(kind)
                        const needsLength = ['SMA', 'EMA', 'RSI', 'STDDEV', 'ATR'].includes(kind)
                        const showTimeframe = kind !== 'CUSTOM'
                        const sourceKey = kind === 'VWAP' ? 'price' : 'source'
                        const sourceValue =
                          kind === 'VWAP'
                            ? String(params.price ?? params.source ?? 'hlc3')
                            : String(params.source ?? params.price ?? 'close')
                        const sourceOptions =
                          kind === 'VWAP'
                            ? ['hlc3', 'close', 'open', 'high', 'low']
                            : ['close', 'open', 'high', 'low', 'hlc3', 'volume']
                        return (
                          <Stack key={idx} direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
                            <FormControlLabel
                              sx={{ mr: 0 }}
                              control={
                                <Checkbox
                                  checked={row.enabled}
                                  onChange={(e) =>
                                    setIndicatorRows((prev) =>
                                      prev.map((r, i) => (i === idx ? { ...r, enabled: e.target.checked } : r)),
                                    )
                                  }
                                />
                              }
                              label=""
                            />
                            <Box
                              aria-label="Indicator color"
                              sx={{
                                width: 12,
                                height: 12,
                                borderRadius: '50%',
                                border: `1px solid ${theme.palette.divider}`,
                                backgroundColor: swatchColor ?? 'transparent',
                                alignSelf: { xs: 'flex-start', md: 'center' },
                                mt: { xs: 0.5, md: 0 },
                              }}
                            />
                            <TextField
                              label="Name"
                              size="small"
                              value={row.name}
                              onChange={(e) =>
                                setIndicatorRows((prev) =>
                                  prev.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r)),
                                )
                              }
                              sx={{ minWidth: 160, flex: 1 }}
                            />
                            <TextField
                              label="Type"
                              select
                              size="small"
                              value={kind}
                              onChange={(e) =>
                                setIndicatorRows((prev) =>
                                  prev.map((r, i) =>
                                    i === idx
                                      ? (() => {
                                          const nextKind = String(e.target.value || '').toUpperCase()
                                          let nextParams: Record<string, any> = { ...params }
                                          if (nextKind === 'VWAP') {
                                            const price =
                                              nextParams.price ?? nextParams.source ?? 'hlc3'
                                            const { source: _source, ...rest } = nextParams
                                            nextParams = { ...rest, price }
                                          } else {
                                            const source =
                                              nextParams.source ?? nextParams.price ?? 'close'
                                            const { price: _price, ...rest } = nextParams
                                            nextParams = { ...rest, source }
                                          }
                                          return { ...r, kind: nextKind, params: nextParams }
                                        })()
                                      : r,
                                  ),
                                )
                              }
                              sx={{ minWidth: 140 }}
                            >
                              {['SMA', 'EMA', 'RSI', 'STDDEV', 'ATR', 'RET', 'OBV', 'VWAP', 'CUSTOM'].map((k) => (
                                <MenuItem key={k} value={k}>{k}</MenuItem>
                              ))}
                            </TextField>
                            <TextField
                              label="Plot"
                              select
                              size="small"
                              value={row.plot}
                              onChange={(e) =>
                                setIndicatorRows((prev) =>
                                  prev.map((r, i) => (i === idx ? { ...r, plot: e.target.value as any } : r)),
                                )
                              }
                              sx={{ minWidth: 120 }}
                            >
                              <MenuItem value="price">Price</MenuItem>
                              <MenuItem value="hidden">Hidden</MenuItem>
                            </TextField>

                            {kind === 'CUSTOM' ? (
                              <>
                                <Autocomplete
                                  options={customIndicators}
                                  loading={customIndicatorsLoading}
                                  value={
                                    customIndicators.find(
                                      (ci) =>
                                        ci.name.toUpperCase() ===
                                        String(params.function ?? '').toUpperCase(),
                                    ) ?? null
                                  }
                                  onChange={(_e, value) =>
                                    setIndicatorRows((prev) =>
                                      prev.map((r, i) =>
                                        i === idx
                                          ? { ...r, kind: 'CUSTOM', params: { ...params, function: value?.name ?? '' } }
                                          : r,
                                      ),
                                    )
                                  }
                                  getOptionLabel={(o) => o.name}
                                  isOptionEqualToValue={(a, b) => a.id === b.id}
                                  renderInput={(p) => (
                                    <TextField {...p} label="Function" size="small" sx={{ minWidth: 240 }} />
                                  )}
                                />
                                <TextField
                                  label="Args (comma-separated DSL)"
                                  size="small"
                                  value={(Array.isArray(params.args) ? params.args : []).join(', ')}
                                  onChange={(e) => {
                                    const args = e.target.value
                                      .split(',')
                                      .map((s) => s.trim())
                                      .filter(Boolean)
                                    setIndicatorRows((prev) =>
                                      prev.map((r, i) =>
                                        i === idx ? { ...r, params: { ...params, args } } : r,
                                      ),
                                    )
                                  }}
                                  sx={{ minWidth: 260, flex: 1 }}
                                />
                              </>
                            ) : (
                              <>
                                {needsSourceOrPrice ? (
                                <TextField
                                  label={kind === 'VWAP' ? 'Price' : 'Source'}
                                  select
                                  size="small"
                                  value={sourceValue}
                                  onChange={(e) =>
                                    setIndicatorRows((prev) =>
                                      prev.map((r, i) =>
                                        i === idx
                                          ? { ...r, params: { ...params, [sourceKey]: e.target.value } }
                                          : r,
                                      ),
                                    )
                                  }
                                  sx={{ minWidth: 120 }}
                                >
                                  {sourceOptions.map((s) => (
                                    <MenuItem key={s} value={s}>{s}</MenuItem>
                                  ))}
                                </TextField>
                                ) : null}
                              </>
                            )}

                            {needsLength && kind !== 'RET' && kind !== 'CUSTOM' && (
                              <TextField
                                label="Length"
                                size="small"
                                type="number"
                                value={Number(params.length ?? 14)}
                                onChange={(e) =>
                                  setIndicatorRows((prev) =>
                                    prev.map((r, i) =>
                                      i === idx ? { ...r, params: { ...params, length: Number(e.target.value || 0) } } : r,
                                    ),
                                  )
                                }
                                sx={{ width: 110 }}
                              />
                            )}

                            {showTimeframe ? (
                              <TextField
                                label="TF"
                                select
                                size="small"
                                value={String(params.timeframe ?? '1d')}
                                onChange={(e) =>
                                  setIndicatorRows((prev) =>
                                    prev.map((r, i) =>
                                      i === idx ? { ...r, params: { ...params, timeframe: e.target.value } } : r,
                                    ),
                                  )
                                }
                                sx={{ width: 90 }}
                              >
                                <MenuItem value="1d">1d</MenuItem>
                              </TextField>
                            ) : null}

                            <Button
                              size="small"
                              color="error"
                              onClick={() =>
                                setIndicatorRows((prev) => prev.filter((_r, i) => i !== idx))
                              }
                            >
                              Remove
                            </Button>
                          </Stack>
                        )
                      })}
                    </Stack>
                  </Stack>
                </AccordionDetails>
              </Accordion>
              <Accordion disableGutters defaultExpanded={false}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">DSL signals</Typography>
                  <Box sx={{ flex: 1 }} />
                  <Tooltip title="DSL expression help (functions/metrics/keywords)">
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        openExprHelpForSignals()
                      }}
                    >
                      <HelpOutlineIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={1}>
                    <DslEditor
                      languageId="sigma-dsl-dashboard"
                      value={signalDsl}
                      onChange={(v) => setSignalDsl(v)}
                      height={140}
                      operands={signalOperandOptions}
                      customIndicators={customIndicators.map((ci) => ({
                        id: ci.id,
                        name: ci.name,
                        params: ci.params || [],
                        description: ci.description || null,
                      }))}
                      onCtrlEnter={() => void runSignals()}
                      onEditorMount={(editor) => {
                        signalDslEditorRef.current = editor
                      }}
                    />
	                    <Stack direction="row" spacing={1} alignItems="center">
	                      <Button
	                        size="small"
	                        variant="outlined"
	                        onClick={() => setStrategyDialogOpen(true)}
	                      >
	                        Load strategy
	                      </Button>
	                      <Button
	                        size="small"
	                        variant="contained"
	                        onClick={() => void runSignals()}
	                        disabled={signalLoading}
	                      >
                        {signalLoading ? 'Running…' : 'Run'}
                      </Button>
                      <Button
                        size="small"
                        onClick={() => {
                          setSignalDsl('')
                          setSignalMarkers([])
                          setSignalError(null)
                        }}
                      >
                        Clear
                      </Button>
                      <Box sx={{ flex: 1 }} />
                      <Typography variant="caption" color="text.secondary">
                        Ctrl+Enter to run
                      </Typography>
                    </Stack>
                    {signalError && (
                      <Typography variant="caption" color="error">
                        {signalError}
                      </Typography>
                    )}
                    {signalMarkers.length > 0 && (
                      <Typography variant="caption" color="text.secondary">
                        Markers: {signalMarkers.length}
                      </Typography>
                    )}
                  </Stack>
                </AccordionDetails>
              </Accordion>
              */}
            </Stack>
	          </Paper>
      </Box>

      <Box sx={{ mt: 2 }}>
        <HoldingsSummaryHistoryPanel
          chartDisplayMode={holdingsHistoryChartDisplayMode}
          onChartDisplayModeChange={setHoldingsHistoryChartDisplayMode}
        />
      </Box>
    </Box>
  )
}
