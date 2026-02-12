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
import MenuItem from '@mui/material/MenuItem'
import { useTheme } from '@mui/material/styles'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ColorType,
  CrosshairMode,
  PriceScaleMode,
  createChart,
  type BusinessDay,
  type IChartApi,
  type LineData,
} from 'lightweight-charts'

import {
  captureHoldingsSummarySnapshot,
  fetchHoldingsSummarySnapshots,
  fetchHoldingsSummarySnapshotsMeta,
  type HoldingsSummarySnapshot,
} from '../services/holdingsSummarySnapshots'

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

function toBusinessDay(dateIso: string): BusinessDay {
  const [y, m, d] = String(dateIso || '').split('-').map((v) => Number(v))
  return { year: y || 1970, month: m || 1, day: d || 1 }
}

function nowIstMinutesOfDay(): number {
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(new Date())
    const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? '0')
    const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? '0')
    return hour * 60 + minute
  } catch {
    return 0
  }
}

function prevTradingDayIso(dateIso: string): string {
  const [y, m, d] = String(dateIso || '').split('-').map((v) => Number(v))
  let dt = new Date(Date.UTC(y || 1970, (m || 1) - 1, d || 1))
  do {
    dt = new Date(dt.getTime() - 24 * 60 * 60 * 1000)
  } while (dt.getUTCDay() === 0 || dt.getUTCDay() === 6) // Sun/Sat

  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

function preopenFinalizeAsOfDate(todayIso: string): string | null {
  // Daily snapshot should represent a stable "previous trading day" baseline.
  // Before 09:00 IST, finalize yesterday instead of capturing an intraday row.
  const [y, m, d] = String(todayIso || '').split('-').map((v) => Number(v))
  const today = new Date(Date.UTC(y || 1970, (m || 1) - 1, d || 1))
  if (today.getUTCDay() === 0 || today.getUTCDay() === 6) return null // weekends

  const mins = nowIstMinutesOfDay()
  if (mins >= 9 * 60) return null
  return prevTradingDayIso(todayIso)
}

function HoldingsLineChart({
  series,
  height = 260,
  displayMode = 'value',
  leftScaleVisible = false,
}: {
  series: Array<{ label: string; color: string; data: LineData[]; priceScaleId?: 'left' | 'right' }>
  height?: number
  displayMode?: 'value' | 'pct'
  leftScaleVisible?: boolean
}) {
  const theme = useTheme()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRefs = useRef<any[]>([])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: theme.palette.text.secondary,
        fontFamily: theme.typography.fontFamily,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: 'transparent' },
        horzLines: {
          color:
            theme.palette.mode === 'dark'
              ? 'rgba(255,255,255,0.08)'
              : 'rgba(0,0,0,0.06)',
        },
      },
      crosshair: { mode: CrosshairMode.Normal },
      leftPriceScale: { visible: leftScaleVisible, borderColor: 'transparent' },
      rightPriceScale: { visible: true, borderColor: 'transparent' },
      timeScale: { borderColor: 'transparent', timeVisible: true },
    })

    chartRef.current = chart
    seriesRefs.current = []

    const resizeObserver = new ResizeObserver(() => {
      chart.timeScale().fitContent()
    })
    resizeObserver.observe(el)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRefs.current = []
    }
  }, [leftScaleVisible, theme])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const mode = displayMode === 'pct' ? PriceScaleMode.Percentage : PriceScaleMode.Normal
    chart.applyOptions({
      leftPriceScale: { mode },
      rightPriceScale: { mode },
    })
  }, [displayMode])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    for (const s of seriesRefs.current) chart.removeSeries(s)
    seriesRefs.current = []

    for (const s of series) {
      const line = chart.addLineSeries({
        color: s.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        priceScaleId: s.priceScaleId || 'right',
      })
      seriesRefs.current.push(line)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      line.setData(s.data as any)
    }
    chart.timeScale().fitContent()
  }, [series])

  return <Box ref={containerRef} sx={{ width: '100%', height }} />
}

export function HoldingsSummaryHistoryPanel({
  chartDisplayMode = 'value',
}: {
  chartDisplayMode?: 'value' | 'pct'
}) {
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
      const todayIso = meta?.today || ''
      const asOf = todayIso ? preopenFinalizeAsOfDate(todayIso) : null
      await captureHoldingsSummarySnapshot({
        broker_name: brokerName,
        ...(asOf ? { as_of_date: asOf } : {}),
      })
      await loadMeta()
      await loadRows()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to capture snapshot.')
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
            const todayIso = range0.max || ''
            const asOf = todayIso ? preopenFinalizeAsOfDate(todayIso) : null
            if (asOf) {
              await captureHoldingsSummarySnapshot({ broker_name: brokerName, as_of_date: asOf })
            }
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

  const hideTodayRow = Boolean(meta?.today && nowIstMinutesOfDay() < 9 * 60)
  const visibleRows = useMemo(() => {
    if (!hideTodayRow || !meta?.today) return rows
    return rows.filter((r) => String(r.as_of_date || '') !== meta.today)
  }, [rows, hideTodayRow, meta?.today])

  const chartData = useMemo(() => {
    const sorted = visibleRows
      .slice()
      .sort((a, b) =>
        String(a.as_of_date || '').localeCompare(String(b.as_of_date || '')),
      )

    const accountSeries: LineData[] = []
    const equitySeries: LineData[] = []
    const fundsSeries: LineData[] = []

    for (const r of sorted) {
      const date = String(r.as_of_date || '').trim()
      if (!date) continue
      const time = toBusinessDay(date)

      const account = r.account_value != null ? Number(r.account_value) : NaN
      if (Number.isFinite(account)) {
        accountSeries.push({ time, value: account })
      }

      const equity = r.equity_value != null ? Number(r.equity_value) : NaN
      if (Number.isFinite(equity)) {
        equitySeries.push({ time, value: equity })
      }

      const funds = r.funds_available != null ? Number(r.funds_available) : NaN
      if (Number.isFinite(funds)) {
        fundsSeries.push({ time, value: funds })
      }
    }

    return { accountSeries, equitySeries, fundsSeries }
  }, [visibleRows])

  const minDate = meta?.min_date || meta?.today || ''
  const maxDate = meta?.today || ''
  const availableTo = hideTodayRow && meta?.today ? prevTradingDayIso(meta.today) : meta?.max_date || meta?.today || ''

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Holdings summary history
        </Typography>
        <FormControlLabel
          control={<Switch checked={autoCapture} onChange={(e) => setAutoCapture(e.target.checked)} />}
          label="Auto-finalize previous day (before 09:00 IST)"
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

      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', lg: 'row' }, gap: 2, mb: 2 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Account value
          </Typography>
          <HoldingsLineChart
            height={260}
            displayMode={chartDisplayMode}
            series={[
              {
                label: 'Account value (cash + equity)',
                color: theme.palette.warning.main,
                data: chartData.accountSeries,
              },
            ]}
          />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Equity vs Funds (dual axis)
          </Typography>
          <HoldingsLineChart
            height={260}
            displayMode={chartDisplayMode}
            leftScaleVisible
            series={[
              {
                label: 'Equity value',
                color: theme.palette.info.main,
                data: chartData.equitySeries,
                priceScaleId: 'left',
              },
              {
                label: 'Funds (cash)',
                color: theme.palette.success.main,
                data: chartData.fundsSeries,
                priceScaleId: 'right',
              },
            ]}
          />
          <Typography variant="caption" color="text.secondary">
            Equity uses the left y-axis; Funds (cash) uses the right y-axis.
          </Typography>
          {chartDisplayMode === 'pct' && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              % mode is relative to the first visible value on each axis (Equity and Funds are scaled independently).
            </Typography>
          )}
        </Box>
      </Box>

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
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleRows.map((r) => (
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
                </TableRow>
              ))}
              {visibleRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={12}>
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
            Data available from {meta.min_date} to {availableTo}.
          </Typography>
        )}
      </Box>
    </Paper>
  )
}
