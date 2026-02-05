import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import FormControlLabel from '@mui/material/FormControlLabel'
import Paper from '@mui/material/Paper'
import Switch from '@mui/material/Switch'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Autocomplete from '@mui/material/Autocomplete'
import MenuItem from '@mui/material/MenuItem'
import { alpha, useTheme } from '@mui/material/styles'
import { useEffect, useMemo, useState } from 'react'

import {
  captureHoldingsSummarySnapshot,
  fetchHoldingsSummarySnapshots,
  fetchHoldingsSummarySnapshotsMeta,
  type HoldingsSummarySnapshot,
} from '../services/holdingsSummarySnapshots'

type ChartPoint = { x: number; y: number }

function parseDateMs(dateIso: string): number {
  return Date.parse(`${dateIso}T00:00:00Z`)
}

function formatCompactInr(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(2)}Cr`
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(2)}L`
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(1)}K`
  return value.toLocaleString('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  })
}

function formatPct(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return `${Number(value).toFixed(digits)}%`
}

function ValueLineChart({
  series,
  height = 260,
}: {
  series: Array<{ label: string; color: string; points: ChartPoint[] }>
  height?: number
}) {
  const theme = useTheme()
  const [hoverX, setHoverX] = useState<number | null>(null)
  const width = 980
  const paddingLeft = 78
  const paddingRight = 18
  const paddingTop = 16
  const paddingBottom = 34

  const all = series.flatMap((s) => s.points)
  if (all.length < 2) {
    return (
      <Typography variant="body2" color="text.secondary">
        No chart data yet.
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
  const uniqX = Array.from(new Set(all.map((p) => p.x))).sort((a, b) => a - b)
  const desiredXTicks = spanDays <= 7 ? 8 : spanDays <= 31 ? 6 : 6
  const step = Math.max(1, Math.floor(uniqX.length / Math.max(2, desiredXTicks - 1)))
  const xTicks: number[] = []
  for (let i = 0; i < uniqX.length; i += step) xTicks.push(uniqX[i]!)
  if (xTicks[0] !== uniqX[0]) xTicks.unshift(uniqX[0]!)
  if (xTicks[xTicks.length - 1] !== uniqX[uniqX.length - 1]) xTicks.push(uniqX[uniqX.length - 1]!)

  const formatDateLabel = (ms: number) => {
    const d = new Date(ms)
    if (spanDays <= 31) {
      return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    }
    return d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
  }

  let hoverDateX: number | null = null
  if (hoverX != null && uniqX.length > 0) {
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
          dateLabel: formatDateLabel(hoverDateX),
          items: paths
            .map((s) => {
              const p = s.points.find((pt) => pt.x === hoverDateX)
              return { label: s.label, color: s.color, y: p?.y ?? null }
            })
            .filter((x) => x.y != null),
        }

  const yTicks = 4
  const grid = Array.from({ length: yTicks + 1 }).map((_, i) => {
    const t = i / yTicks
    const y = paddingTop + t * (height - paddingTop - paddingBottom)
    const yValue = maxY - t * spanY
    return { y, yValue }
  })

  return (
    <Box sx={{ width: '100%', overflowX: 'auto' }}>
      <svg
        width={width}
        height={height}
        style={{ display: 'block' }}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
          const x = e.clientX - rect.left
          setHoverX(((x - paddingLeft) / (width - paddingLeft - paddingRight)) * spanX + minX)
        }}
        onMouseLeave={() => setHoverX(null)}
      >
        {grid.map((g) => (
          <g key={g.y}>
            <line
              x1={paddingLeft}
              x2={width - paddingRight}
              y1={g.y}
              y2={g.y}
              stroke={alpha(theme.palette.text.primary, 0.08)}
              strokeWidth={1}
            />
            <text
              x={paddingLeft - 10}
              y={g.y + 4}
              textAnchor="end"
              fontSize={11}
              fill={alpha(theme.palette.text.primary, 0.7)}
            >
              {formatCompactInr(g.yValue)}
            </text>
          </g>
        ))}

        {xTicks.map((x, i) => (
          <text
            key={x}
            x={scaleX(x)}
            y={height - 10}
            textAnchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'}
            fontSize={11}
            fill={alpha(theme.palette.text.primary, 0.7)}
          >
            {formatDateLabel(x)}
          </text>
        ))}

        {paths.map((p) => (
          <path
            key={p.label}
            d={p.d}
            fill="none"
            stroke={p.color}
            strokeWidth={2.2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}

        {hoverDateX != null && (
          <line
            x1={scaleX(hoverDateX)}
            x2={scaleX(hoverDateX)}
            y1={paddingTop}
            y2={height - paddingBottom}
            stroke={alpha(theme.palette.text.primary, 0.25)}
            strokeWidth={1}
          />
        )}
      </svg>

      {hoverSummary && hoverSummary.items.length > 0 && (
        <Box
          sx={{
            mt: 1,
            display: 'flex',
            flexWrap: 'wrap',
            gap: 1.2,
            alignItems: 'center',
          }}
        >
          <Typography variant="caption" color="text.secondary">
            {hoverSummary.dateLabel}
          </Typography>
          {hoverSummary.items.map((it) => (
            <Box key={it.label} sx={{ display: 'flex', gap: 0.6, alignItems: 'center' }}>
              <Box sx={{ width: 10, height: 10, borderRadius: 10, bgcolor: it.color }} />
              <Typography variant="caption" color="text.secondary">
                {it.label}: {formatCompactInr(Number(it.y))}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  )
}

const CHART_FIELDS: Array<{ key: keyof HoldingsSummarySnapshot; label: string }> = [
  { key: 'equity_value', label: 'Equity value' },
  { key: 'funds_available', label: 'Funds (cash)' },
  { key: 'account_value', label: 'Account value (cash + equity)' },
  { key: 'invested', label: 'Invested' },
]

export function HoldingsSummaryHistoryPanel() {
  const theme = useTheme()
  const [brokerName, setBrokerName] = useState('zerodha')
  const [meta, setMeta] = useState<{ today: string; min_date?: string | null; max_date?: string | null } | null>(null)
  const [rows, setRows] = useState<HoldingsSummarySnapshot[]>([])
  const [loading, setLoading] = useState(false)
  const [captureLoading, setCaptureLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [autoCapture, setAutoCapture] = useState(true)

  const [selectedFields, setSelectedFields] = useState<(keyof HoldingsSummarySnapshot)[]>([
    'equity_value',
    'funds_available',
    'account_value',
  ])

  const loadMeta = async (): Promise<{ min: string; max: string }> => {
    const m = await fetchHoldingsSummarySnapshotsMeta({ broker_name: brokerName })
    setMeta(m)
    const min = m.min_date || m.today
    const max = m.today
    return { min, max }
  }

  const loadRows = async (range?: { start: string; end: string }) => {
    setLoading(true)
    setError(null)
    try {
      const list = await fetchHoldingsSummarySnapshots({
        broker_name: brokerName,
        start_date: range?.start ?? startDate,
        end_date: range?.end ?? endDate,
      })
      setRows(list)
    } catch (err) {
      setRows([])
      setError(err instanceof Error ? err.message : 'Failed to load holdings summary history.')
    } finally {
      setLoading(false)
    }
  }

  const captureNow = async () => {
    setCaptureLoading(true)
    setError(null)
    try {
      await captureHoldingsSummarySnapshot({ broker_name: brokerName })
      await loadMeta()
      await loadRows()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to capture today snapshot.')
    } finally {
      setCaptureLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    const boot = async () => {
      try {
        setRows([])
        setError(null)
        if (!active) return
        const range0 = await loadMeta()
        setStartDate(range0.min)
        setEndDate(range0.max)
        if (autoCapture) {
          try {
            await captureHoldingsSummarySnapshot({ broker_name: brokerName })
          } catch {
            // Ignore auto-capture errors; user can still view history.
          }
          const range1 = await loadMeta()
          setStartDate(range1.min)
          setEndDate(range1.max)
          await loadRows({ start: range1.min, end: range1.max })
          return
        }
        await loadRows({ start: range0.min, end: range0.max })
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load holdings summary history.')
      }
    }
    void boot()
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brokerName])

  const chartSeries = useMemo(() => {
    const colorMap: Record<string, string> = {
      equity_value: theme.palette.info.main,
      funds_available: theme.palette.success.main,
      account_value: theme.palette.warning.main,
      invested: theme.palette.secondary.main,
    }

    return selectedFields
      .map((key) => {
        const label = CHART_FIELDS.find((f) => f.key === key)?.label || String(key)
        const points: ChartPoint[] = rows
          .map((r) => {
            const yRaw = (r as any)[key] as unknown
            const y = yRaw != null ? Number(yRaw) : NaN
            if (!Number.isFinite(y)) return null
            return { x: parseDateMs(r.as_of_date), y }
          })
          .filter(Boolean) as ChartPoint[]
        return {
          label,
          color: colorMap[String(key)] || theme.palette.primary.main,
          points,
        }
      })
      .filter((s) => s.points.length > 0)
  }, [rows, selectedFields, theme.palette])

  const minDate = meta?.min_date || meta?.today || ''
  const maxDate = meta?.today || ''

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Holdings summary history
        </Typography>
        <FormControlLabel
          control={<Switch checked={autoCapture} onChange={(e) => setAutoCapture(e.target.checked)} />}
          label="Auto-capture today"
        />
        <Button variant="outlined" size="small" onClick={() => void captureNow()} disabled={captureLoading}>
          {captureLoading ? 'Capturing…' : 'Capture now'}
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Tracks daily funds (cash), equity value, and derived performance so you can see how cash and equity “dance” to maintain account value.
      </Typography>

      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mb: 2 }}>
        <TextField
          size="small"
          label="Broker"
          select
          value={brokerName}
          onChange={(e) => setBrokerName(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="zerodha">Zerodha (Kite)</MenuItem>
          <MenuItem value="angelone">AngelOne (SmartAPI)</MenuItem>
        </TextField>
        <TextField
          size="small"
          label="Start"
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          inputProps={{ min: minDate, max: maxDate }}
          sx={{ minWidth: 165 }}
        />
        <TextField
          size="small"
          label="End"
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          inputProps={{ min: minDate, max: maxDate }}
          sx={{ minWidth: 165 }}
        />
        <Button
          variant="contained"
          size="small"
          onClick={() => void loadRows({ start: startDate, end: endDate })}
          disabled={!startDate || !endDate || loading}
        >
          Apply
        </Button>
        {loading && <CircularProgress size={18} />}
      </Box>

      <Box sx={{ mb: 2 }}>
        <Autocomplete
          multiple
          size="small"
          options={CHART_FIELDS}
          getOptionLabel={(opt) => opt.label}
          value={CHART_FIELDS.filter((f) => selectedFields.includes(f.key))}
          onChange={(_e, next) => setSelectedFields(next.map((x) => x.key))}
          renderInput={(params) => <TextField {...params} label="Chart columns" />}
        />
      </Box>

      <ValueLineChart series={chartSeries} />

      <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          Snapshots
        </Typography>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Date</TableCell>
                <TableCell align="right">Positions</TableCell>
                <TableCell align="right">Funds</TableCell>
                <TableCell align="right">Equity</TableCell>
                <TableCell align="right">Account</TableCell>
                <TableCell align="right">P&amp;L (total)</TableCell>
                <TableCell align="right">P&amp;L (today)</TableCell>
                <TableCell align="right">Win rate</TableCell>
                <TableCell align="right">Today win</TableCell>
                <TableCell align="right">α (annual)</TableCell>
                <TableCell align="right">β</TableCell>
                <TableCell align="right">CAGR 1Y</TableCell>
                <TableCell align="right">CAGR 2Y</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} hover>
                  <TableCell>{r.as_of_date}</TableCell>
                  <TableCell align="right">{r.holdings_count ?? 0}</TableCell>
                  <TableCell align="right">
                    {r.funds_available != null ? formatCompactInr(Number(r.funds_available)) : '—'}
                  </TableCell>
                  <TableCell align="right">
                    {r.equity_value != null ? formatCompactInr(Number(r.equity_value)) : '—'}
                  </TableCell>
                  <TableCell align="right">
                    {r.account_value != null ? formatCompactInr(Number(r.account_value)) : '—'}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color:
                        r.total_pnl_pct != null && Number(r.total_pnl_pct) > 0
                          ? 'success.main'
                          : r.total_pnl_pct != null && Number(r.total_pnl_pct) < 0
                            ? 'error.main'
                            : 'text.primary',
                    }}
                  >
                    {formatPct(r.total_pnl_pct, 2)}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color:
                        r.today_pnl_pct != null && Number(r.today_pnl_pct) > 0
                          ? 'success.main'
                          : r.today_pnl_pct != null && Number(r.today_pnl_pct) < 0
                            ? 'error.main'
                            : 'text.primary',
                    }}
                  >
                    {formatPct(r.today_pnl_pct, 2)}
                  </TableCell>
                  <TableCell align="right">{formatPct(r.overall_win_rate, 1)}</TableCell>
                  <TableCell align="right">{formatPct(r.today_win_rate, 1)}</TableCell>
                  <TableCell align="right">{formatPct(r.alpha_annual_pct, 2)}</TableCell>
                  <TableCell align="right">
                    {r.beta != null && Number.isFinite(Number(r.beta)) ? Number(r.beta).toFixed(2) : '—'}
                  </TableCell>
                  <TableCell align="right">{formatPct(r.cagr_1y_pct, 1)}</TableCell>
                  <TableCell align="right">{formatPct(r.cagr_2y_pct, 1)}</TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={13}>
                    <Typography variant="body2" color="text.secondary">
                      No snapshots yet. Click “Capture now” after connecting your broker.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>

        {meta?.min_date && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            Data available from {meta.min_date} to {meta.today}.
          </Typography>
        )}
      </Box>
    </Paper>
  )
}
