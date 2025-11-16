import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import {
  fetchAnalyticsTrades,
  fetchAnalyticsSummary,
  rebuildAnalyticsTrades,
  type AnalyticsSummary,
  type AnalyticsTrade,
} from '../services/analytics'
import { fetchStrategies, type Strategy } from '../services/admin'
import { recordAppLog } from '../services/logs'

export function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rebuilding, setRebuilding] = useState(false)
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | 'all'>(
    'all',
  )
  const [dateFrom, setDateFrom] = useState<string>('')
  const [dateTo, setDateTo] = useState<string>('')
  const [trades, setTrades] = useState<AnalyticsTrade[]>([])

  const load = async (opts?: { withStrategies?: boolean }) => {
    try {
      setLoading(true)
      if (opts?.withStrategies) {
        const s = await fetchStrategies()
        setStrategies(s)
      }

      const filters = {
        strategyId:
          selectedStrategyId === 'all' ? null : (selectedStrategyId as number),
        dateFrom: dateFrom || null,
        dateTo: dateTo || null,
      }

      const [summaryData, tradesData] = await Promise.all([
        fetchAnalyticsSummary(filters),
        fetchAnalyticsTrades(filters),
      ])
      setSummary(summaryData)
      setTrades(tradesData)
      setError(null)
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Failed to load analytics'
      setError(msg)
      recordAppLog('ERROR', msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load({ withStrategies: true })
  }, [])

  const handleRebuild = async () => {
    setRebuilding(true)
    try {
      await rebuildAnalyticsTrades()
      await load()
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Failed to rebuild analytics trades'
      setError(msg)
      recordAppLog('ERROR', msg)
    } finally {
      setRebuilding(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Analytics
      </Typography>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', md: 'center' },
          mb: 3,
          gap: 2,
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography color="text.secondary">
            Strategy-level P&amp;L and basic performance metrics. Use Rebuild to
            re-generate trades from executed orders.
          </Typography>
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 1.5,
              alignItems: 'center',
            }}
          >
            <TextField
              select
              size="small"
              label="Strategy"
              value={selectedStrategyId}
              onChange={(e) =>
                setSelectedStrategyId(
                  e.target.value === 'all'
                    ? 'all'
                    : Number(e.target.value),
                )
              }
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="all">All strategies</MenuItem>
              {strategies.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="From"
              type="date"
              size="small"
              InputLabelProps={{ shrink: true }}
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
            <TextField
              label="To"
              type="date"
              size="small"
              InputLabelProps={{ shrink: true }}
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                void load()
              }}
              disabled={loading}
            >
              Apply filters
            </Button>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            size="small"
            variant="outlined"
            onClick={handleRebuild}
            disabled={loading || rebuilding}
          >
            {rebuilding ? 'Rebuilding…' : 'Rebuild trades'}
          </Button>
        </Box>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading analytics…</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {summary ? (
            <Paper sx={{ p: 2, maxWidth: 480 }}>
              <Typography variant="h6" gutterBottom>
                Overall Summary
              </Typography>
              <Typography variant="body2">
                Trades: <strong>{summary.trades}</strong>
              </Typography>
              <Typography variant="body2">
                Total P&amp;L:{' '}
                <strong>{summary.total_pnl.toFixed(2)}</strong>
              </Typography>
              <Typography variant="body2">
                Win rate:{' '}
                <strong>{(summary.win_rate * 100).toFixed(1)}%</strong>
              </Typography>
              <Typography variant="body2">
                Avg win:{' '}
                <strong>
                  {summary.avg_win != null ? summary.avg_win.toFixed(2) : '-'}
                </strong>
              </Typography>
              <Typography variant="body2">
                Avg loss:{' '}
                <strong>
                  {summary.avg_loss != null
                    ? summary.avg_loss.toFixed(2)
                    : '-'}
                </strong>
              </Typography>
              <Typography variant="body2">
                Max drawdown:{' '}
                <strong>{summary.max_drawdown.toFixed(2)}</strong>
              </Typography>
            </Paper>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No analytics yet. Execute some trades, then rebuild trades to see
              P&amp;L.
            </Typography>
          )}

          <TradesSection trades={trades} />
        </Box>
      )}
    </Box>
  )
}

type TradesSectionProps = {
  trades: AnalyticsTrade[]
}

const formatIst = (iso: string): string => {
  const utc = new Date(iso)
  const istMs = utc.getTime() + 5.5 * 60 * 60 * 1000
  const ist = new Date(istMs)
  return ist.toLocaleString('en-IN')
}

function TradesSection({ trades }: TradesSectionProps) {
  if (!trades.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No trades in the selected range.
      </Typography>
    )
  }

  // Build cumulative P&L series.
  const cumPoints = trades.reduce(
    (acc, t, index) => {
      const prev = acc.length ? acc[acc.length - 1].y : 0
      const next = prev + t.pnl
      acc.push({ x: index, y: next })
      return acc
    },
    [] as { x: number; y: number }[],
  )

  const pnlBySymbol = trades.reduce((map, t) => {
    map[t.symbol] = (map[t.symbol] ?? 0) + t.pnl
    return map
  }, {} as Record<string, number>)

  const symbolBars = Object.entries(pnlBySymbol).map(([label, value]) => ({
    label,
    value,
  }))

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          gap: 2,
        }}
      >
        <Paper sx={{ p: 2, flex: 1, minWidth: 260 }}>
          <Typography variant="subtitle1" gutterBottom>
            Cumulative P&amp;L over trades
          </Typography>
          <MiniLineChart points={cumPoints} />
        </Paper>
        <Paper sx={{ p: 2, flex: 1, minWidth: 260 }}>
          <Typography variant="subtitle1" gutterBottom>
            P&amp;L by symbol
          </Typography>
          <MiniBarChart bars={symbolBars} />
        </Paper>
      </Box>

      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle1" gutterBottom>
          Trades
        </Typography>
        <Box sx={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                  Closed At
                </th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                  Strategy
                </th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                  Symbol
                </th>
                <th style={{ textAlign: 'right', padding: '4px 8px' }}>
                  P&amp;L
                </th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id}>
                  <td style={{ padding: '4px 8px' }}>
                    {formatIst(t.closed_at)}
                  </td>
                  <td style={{ padding: '4px 8px' }}>
                    {t.strategy_name ?? '-'}
                  </td>
                  <td style={{ padding: '4px 8px' }}>{t.symbol}</td>
                  <td
                    style={{
                      padding: '4px 8px',
                      textAlign: 'right',
                      color: t.pnl >= 0 ? '#4caf50' : '#f44336',
                    }}
                  >
                    {t.pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Box>
      </Paper>
    </Box>
  )
}

type ChartPoint = { x: number; y: number }

type MiniLineChartProps = {
  points: ChartPoint[]
  width?: number
  height?: number
}

function MiniLineChart({
  points,
  width = 320,
  height = 160,
}: MiniLineChartProps) {
  if (points.length < 2) {
    return (
      <Typography variant="body2" color="text.secondary">
        Not enough trades to plot.
      </Typography>
    )
  }

  const padding = 16
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)

  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1

  const scaleX = (x: number) =>
    padding + ((x - minX) / spanX) * (width - 2 * padding)
  const scaleY = (y: number) =>
    height - padding - ((y - minY) / spanY) * (height - 2 * padding)

  const d = points
    .map((p, i) => {
      const x = scaleX(p.x)
      const y = scaleY(p.y)
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')

  return (
    <svg width={width} height={height}>
      <path
        d={d}
        fill="none"
        stroke="#42a5f5"
        strokeWidth={2}
        strokeLinecap="round"
      />
    </svg>
  )
}

type MiniBarChartProps = {
  bars: { label: string; value: number }[]
  width?: number
  height?: number
}

function MiniBarChart({
  bars,
  width = 320,
  height = 160,
}: MiniBarChartProps) {
  if (!bars.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No data to plot.
      </Typography>
    )
  }

  const padding = 16
  const maxAbs = Math.max(...bars.map((b) => Math.abs(b.value))) || 1
  const barWidth =
    (width - 2 * padding) / Math.max(bars.length, 1) - 4 /* gap */

  const zeroY = height / 2

  return (
    <svg width={width} height={height}>
      {bars.map((b, index) => {
        const x = padding + index * (barWidth + 4)
        const scaledHeight = (Math.abs(b.value) / maxAbs) * (height / 2 - 8)
        const y = b.value >= 0 ? zeroY - scaledHeight : zeroY
        const color = b.value >= 0 ? '#4caf50' : '#f44336'
        return (
          <g key={b.label}>
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={scaledHeight}
              fill={color}
            />
          </g>
        )
      })}
    </svg>
  )
}
