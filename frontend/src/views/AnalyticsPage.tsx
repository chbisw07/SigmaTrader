import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import {
  DataGrid,
  GridToolbar,
  type GridColDef,
} from '@mui/x-data-grid'

import {
  fetchAnalyticsTrades,
  fetchAnalyticsSummary,
  rebuildAnalyticsTrades,
  fetchHoldingsCorrelation,
  type AnalyticsSummary,
  type AnalyticsTrade,
  type HoldingsCorrelationResult,
  type SymbolCorrelationStats,
} from '../services/analytics'
import { fetchStrategies, type Strategy } from '../services/admin'
import { recordAppLog } from '../services/logs'

const CORR_SETTINGS_STORAGE_KEY = 'st_analytics_corr_settings_v1'
const CORR_RESULT_STORAGE_KEY = 'st_analytics_corr_result_v1'
const DEFAULT_CORR_WINDOW_DAYS = '90'
const DEFAULT_CORR_THRESHOLD = '0.6'

export function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rebuilding, setRebuilding] = useState(false)
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | 'all'>(
    'all',
  )
  const [includeSimulated, setIncludeSimulated] = useState<boolean>(false)
  const [dateFrom, setDateFrom] = useState<string>('')
  const [dateTo, setDateTo] = useState<string>('')
  const [trades, setTrades] = useState<AnalyticsTrade[]>([])
  const [corrWindowDays, setCorrWindowDays] = useState<string>(() => {
    if (typeof window === 'undefined') return DEFAULT_CORR_WINDOW_DAYS
    try {
      const raw = window.localStorage.getItem(CORR_SETTINGS_STORAGE_KEY)
      if (!raw) return DEFAULT_CORR_WINDOW_DAYS
      const parsed = JSON.parse(raw) as {
        windowDays?: string
        threshold?: string
      }
      return parsed.windowDays ?? DEFAULT_CORR_WINDOW_DAYS
    } catch {
      return DEFAULT_CORR_WINDOW_DAYS
    }
  })
  const [corrLoading, setCorrLoading] = useState(false)
  const [corrError, setCorrError] = useState<string | null>(null)
  const [corrResult, setCorrResult] =
    useState<HoldingsCorrelationResult | null>(() => {
      if (typeof window === 'undefined') return null
      try {
        const raw = window.localStorage.getItem(CORR_RESULT_STORAGE_KEY)
        if (!raw) return null
        return JSON.parse(raw) as HoldingsCorrelationResult
      } catch {
        return null
      }
    })

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
        includeSimulated,
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
            <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="checkbox"
                checked={includeSimulated}
                onChange={(e) => setIncludeSimulated(e.target.checked)}
              />
              <Typography variant="body2">
                Include paper (simulated) trades
              </Typography>
            </label>
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
          <CorrelationSection
            windowDays={corrWindowDays}
            setWindowDays={setCorrWindowDays}
            loading={corrLoading}
            error={corrError}
            result={corrResult}
            onRefresh={async ({ clusterThreshold }) => {
              try {
                setCorrLoading(true)
                setCorrError(null)
                const windowDaysNum = Number(corrWindowDays) || 90
                const data = await fetchHoldingsCorrelation({
                  windowDays: windowDaysNum,
                  clusterThreshold,
                })
                setCorrResult(data)
                if (typeof window !== 'undefined') {
                  try {
                    window.localStorage.setItem(
                      CORR_RESULT_STORAGE_KEY,
                      JSON.stringify(data),
                    )
                  } catch {
                    // Ignore persistence errors.
                  }
                }
              } catch (err) {
                setCorrError(
                  err instanceof Error
                    ? err.message
                    : 'Failed to load holdings correlation',
                )
              } finally {
                setCorrLoading(false)
              }
            }}
          />
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

type CorrelationSectionProps = {
  windowDays: string
  setWindowDays: (value: string) => void
  loading: boolean
  error: string | null
  result: HoldingsCorrelationResult | null
  onRefresh: (opts: { clusterThreshold: number }) => void
}

function CorrelationSection({
  windowDays,
  setWindowDays,
  loading,
  error,
  result,
  onRefresh,
}: CorrelationSectionProps) {
  const [highlightThreshold, setHighlightThreshold] = useState<string>(() => {
    if (typeof window === 'undefined') return DEFAULT_CORR_THRESHOLD
    try {
      const raw = window.localStorage.getItem(CORR_SETTINGS_STORAGE_KEY)
      if (!raw) return DEFAULT_CORR_THRESHOLD
      const parsed = JSON.parse(raw) as {
        windowDays?: string
        threshold?: string
      }
      return (
        (parsed as { highlightThreshold?: string }).highlightThreshold
        ?? parsed.threshold
        ?? DEFAULT_CORR_THRESHOLD
      )
    } catch {
      return DEFAULT_CORR_THRESHOLD
    }
  })
  const [clusterThreshold, setClusterThreshold] = useState<string>(() => {
    if (typeof window === 'undefined') return DEFAULT_CORR_THRESHOLD
    try {
      const raw = window.localStorage.getItem(CORR_SETTINGS_STORAGE_KEY)
      if (!raw) return DEFAULT_CORR_THRESHOLD
      const parsed = JSON.parse(raw) as {
        windowDays?: string
        threshold?: string
        clusterThreshold?: string
      }
      return (
        parsed.clusterThreshold
        ?? parsed.threshold
        ?? DEFAULT_CORR_THRESHOLD
      )
    } catch {
      return DEFAULT_CORR_THRESHOLD
    }
  })
  const [showHeatmap, setShowHeatmap] = useState(false)

  const highlightNum = Number(highlightThreshold) || 0.6

  const positivePairs: { x: string; y: string; corr: number }[] = []
  const negativePairs: { x: string; y: string; corr: number }[] = []

  if (result && result.matrix.length > 0) {
    const { symbols, matrix } = result
    for (let i = 0; i < symbols.length; i += 1) {
      for (let j = i + 1; j < symbols.length; j += 1) {
        const val = matrix[i]?.[j]
        if (val == null) continue
        if (val >= highlightNum) {
          positivePairs.push({ x: symbols[i], y: symbols[j], corr: val })
        } else if (val <= -highlightNum) {
          negativePairs.push({ x: symbols[i], y: symbols[j], corr: val })
        }
      }
    }
    positivePairs.sort((a, b) => b.corr - a.corr)
    negativePairs.sort((a, b) => a.corr - b.corr)
  }

  // Persist correlation settings so that lookback and highlight threshold
  // survive page reloads.
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(CORR_SETTINGS_STORAGE_KEY)
      let existing: {
        windowDays?: string
        threshold?: string
        highlightThreshold?: string
        clusterThreshold?: string
      } = {}
      if (raw) {
        try {
          existing = JSON.parse(raw) as typeof existing
        } catch {
          existing = {}
        }
      }
      const next = {
        ...existing,
        windowDays,
        highlightThreshold,
        clusterThreshold,
      }
      window.localStorage.setItem(
        CORR_SETTINGS_STORAGE_KEY,
        JSON.stringify(next),
      )
    } catch {
      // Ignore persistence errors.
    }
  }, [windowDays, highlightThreshold, clusterThreshold])

  return (
    <Paper sx={{ p: 2 }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
          flexWrap: 'wrap',
          gap: 2,
          mb: 2,
        }}
      >
        <Box>
          <Typography variant="h6" gutterBottom>
            Holdings correlation &amp; diversification
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Based on daily returns for your current holdings over the selected
            lookback window.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <TextField
            label="Lookback (days)"
            size="small"
            type="number"
            sx={{ width: 140 }}
            value={windowDays}
            onChange={(e) => setWindowDays(e.target.value)}
            InputProps={{ inputProps: { min: 30, max: 730 } }}
          />
          <TextField
            label="Highlight |corr| ≥"
            size="small"
            type="number"
            sx={{ width: 140 }}
            value={highlightThreshold}
            onChange={(e) => setHighlightThreshold(e.target.value)}
            InputProps={{ inputProps: { min: 0, max: 1, step: 0.05 } }}
          />
          <TextField
            label="Cluster corr ≥"
            size="small"
            type="number"
            sx={{ width: 140 }}
            value={clusterThreshold}
            onChange={(e) => setClusterThreshold(e.target.value)}
            InputProps={{ inputProps: { min: 0, max: 1, step: 0.05 } }}
          />
          <Button
            size="small"
            variant="text"
            onClick={() => {
              setWindowDays(DEFAULT_CORR_WINDOW_DAYS)
              setHighlightThreshold(DEFAULT_CORR_THRESHOLD)
              setClusterThreshold(DEFAULT_CORR_THRESHOLD)
            }}
          >
            Reset
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => {
              const clusterNum = Number(clusterThreshold) || 0.6
              onRefresh({ clusterThreshold: clusterNum })
            }}
            disabled={loading}
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </Button>
          <Button
            size="small"
            variant="text"
            onClick={() => setShowHeatmap((prev) => !prev)}
          >
            {showHeatmap ? 'Hide heatmap' : 'Show heatmap'}
          </Button>
        </Box>
      </Box>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      {!result ? (
        <Typography variant="body2" color="text.secondary">
          No correlation analysis available yet.
        </Typography>
      ) : result.matrix.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {result.summary}
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {result.clusters && result.clusters.length > 0 && (
            <ClusterSummaryCards clusters={result.clusters} />
          )}
          <Box>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              {result.summary}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Observations used:
              {' '}
              <strong>{result.observations}</strong>
              {' · '}
              Average correlation:
              {' '}
              <strong>
                {result.average_correlation != null
                  ? result.average_correlation.toFixed(2)
                  : '—'}
              </strong>
              {result.effective_independent_bets != null && (
                <>
                  {' · '}
                  Approx. independent clusters:
                  {' '}
                  <strong>
                    {result.effective_independent_bets.toFixed(1)}
                  </strong>
                </>
              )}
            </Typography>
          </Box>
          {result.recommendations.length > 0 && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                Diversification suggestions
              </Typography>
              {result.recommendations.map((rec) => (
                <Typography
                  key={rec}
                  variant="body2"
                  color="text.secondary"
                >
                  •
                  {' '}
                  {rec}
                </Typography>
              ))}
            </Box>
          )}
          {result.symbol_stats && result.symbol_stats.length > 0 && (
            <SymbolCorrelationStatsTable stats={result.symbol_stats} />
          )}
          {showHeatmap && (
            <HoldingsCorrelationHeatmap
              symbols={result.symbols}
              matrix={result.matrix}
            />
          )}
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              gap: 2,
            }}
          >
            <CorrelationPairsTable
              title="Highly positively correlated pairs"
              pairs={positivePairs}
              emptyMessage="No pairs exceed the positive correlation threshold."
            />
            <CorrelationPairsTable
              title="Strongly negative (diversifying) pairs"
              pairs={negativePairs}
              emptyMessage="No pairs exceed the negative correlation threshold (in absolute value)."
            />
          </Box>
        </Box>
      )}
    </Paper>
  )
}

type HeatmapProps = {
  symbols: string[]
  matrix: (number | null)[][]
}

function colorForCorrelation(value: number | null): string {
  if (value == null) return '#f5f5f5'
  const v = Math.max(-1, Math.min(1, value))
  if (v >= 0) {
    const intensity = v
    const g = Math.round(255 * (1 - intensity))
    const b = Math.round(255 * (1 - intensity))
    return `rgb(255, ${g}, ${b})`
  }
  const intensity = -v
  const r = Math.round(255 * (1 - intensity))
  const g = Math.round(255 * (1 - intensity))
  return `rgb(${r}, ${g}, 255)`
}

function HoldingsCorrelationHeatmap({ symbols, matrix }: HeatmapProps) {
  if (!symbols.length || !matrix.length) return null

  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Box
        component="table"
        sx={{
          borderCollapse: 'collapse',
          minWidth: 360,
        }}
      >
        <Box component="thead">
          <Box component="tr">
            <Box component="th" sx={{ p: 0.5 }} />
            {symbols.map((sym) => (
              <Box
                key={sym}
                component="th"
                sx={{
                  p: 0.5,
                  fontSize: 11,
                  textAlign: 'center',
                  whiteSpace: 'nowrap',
                }}
              >
                {sym}
              </Box>
            ))}
          </Box>
        </Box>
        <Box component="tbody">
          {symbols.map((symRow, i) => (
            <Box component="tr" key={symRow}>
              <Box
                component="td"
                sx={{
                  p: 0.5,
                  fontSize: 11,
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                }}
              >
                {symRow}
              </Box>
              {symbols.map((symCol, j) => {
                const val = matrix[i]?.[j] ?? null
                const bg = colorForCorrelation(val)
                const textColor =
                  val != null && Math.abs(val) > 0.7 ? '#fff' : '#000'
                return (
                  <Box
                    key={`${symRow}-${symCol}`}
                    component="td"
                    sx={{
                      width: 42,
                      height: 32,
                      textAlign: 'center',
                      fontSize: 11,
                      bgcolor: bg,
                      color: textColor,
                      border: '1px solid rgba(0,0,0,0.04)',
                    }}
                  >
                    {val != null ? val.toFixed(2) : '–'}
                  </Box>
                )
              })}
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  )
}

type CorrelationPairsTableProps = {
  title: string
  pairs: { x: string; y: string; corr: number }[]
  emptyMessage: string
}

function CorrelationPairsTable({
  title,
  pairs,
  emptyMessage,
}: CorrelationPairsTableProps) {
  return (
    <Paper sx={{ p: 2, flex: 1, minWidth: 260 }}>
      <Typography variant="subtitle2" gutterBottom>
        {title}
      </Typography>
      {pairs.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyMessage}
        </Typography>
      ) : (
        <Box sx={{ maxHeight: 220, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th
                  style={{
                    textAlign: 'left',
                    padding: '4px 8px',
                    fontSize: 12,
                  }}
                >
                  Symbol A
                </th>
                <th
                  style={{
                    textAlign: 'left',
                    padding: '4px 8px',
                    fontSize: 12,
                  }}
                >
                  Symbol B
                </th>
                <th
                  style={{
                    textAlign: 'right',
                    padding: '4px 8px',
                    fontSize: 12,
                  }}
                >
                  Corr
                </th>
              </tr>
            </thead>
            <tbody>
              {pairs.map((p) => (
                <tr key={`${p.x}-${p.y}`}>
                  <td style={{ padding: '4px 8px', fontSize: 12 }}>{p.x}</td>
                  <td style={{ padding: '4px 8px', fontSize: 12 }}>{p.y}</td>
                  <td
                    style={{
                      padding: '4px 8px',
                      textAlign: 'right',
                      fontSize: 12,
                      color:
                        p.corr >= 0
                          ? p.corr >= 0.6
                            ? '#d32f2f'
                            : '#1976d2'
                          : p.corr <= -0.6
                            ? '#1565c0'
                            : '#388e3c',
                    }}
                  >
                    {p.corr.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Box>
      )}
    </Paper>
  )
}

type ClusterSummaryCardsProps = {
  clusters: {
    id: string
    symbols: string[]
    weight_fraction: number | null
    average_internal_correlation: number | null
    average_to_others: number | null
  }[]
}

function ClusterSummaryCards({ clusters }: ClusterSummaryCardsProps) {
  if (!clusters.length) return null

  const sorted = [...clusters].sort(
    (a, b) => (b.weight_fraction ?? 0) - (a.weight_fraction ?? 0),
  )

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        gap: 1.5,
        mb: 1,
        flexWrap: 'wrap',
      }}
    >
      {sorted.map((c) => {
        const weightPct =
          c.weight_fraction != null ? c.weight_fraction * 100 : null
        const internal =
          c.average_internal_correlation != null
            ? c.average_internal_correlation.toFixed(2)
            : '—'
        const cross =
          c.average_to_others != null
            ? c.average_to_others.toFixed(2)
            : '—'
        return (
          <Paper
            key={c.id}
            sx={{
              p: 1.25,
              minWidth: 180,
              flex: '0 0 auto',
            }}
          >
            <Typography variant="subtitle2" sx={{ mb: 0.25 }}>
              Cluster
              {' '}
              {c.id}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Weight:
              {' '}
              <strong>
                {weightPct != null ? `${weightPct.toFixed(1)}%` : '—'}
              </strong>
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Avg internal corr:
              {' '}
              <strong>{internal}</strong>
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Avg vs others:
              {' '}
              <strong>{cross}</strong>
            </Typography>
          </Paper>
        )
      })}
    </Box>
  )
}

type SymbolCorrelationStatsTableProps = {
  stats: SymbolCorrelationStats[]
}

function SymbolCorrelationStatsTable({
  stats,
}: SymbolCorrelationStatsTableProps) {
  if (!stats.length) return null

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        Per-symbol correlation profile
      </Typography>
      <Box sx={{ height: 320, width: '100%' }}>
        <DataGrid
          rows={stats.map((s) => ({
            id: s.symbol,
            symbol: s.symbol,
            role: s.role ?? '—',
            cluster: s.cluster ?? '—',
            weightDisplay:
              s.weight_fraction != null
                ? `${(s.weight_fraction * 100).toFixed(1)}%`
                : '—',
            avgCorrDisplay:
              s.average_correlation != null
                ? s.average_correlation.toFixed(2)
                : '—',
            mostCorrelatedDisplay:
              s.most_correlated_symbol && s.most_correlated_value != null
                ? `${s.most_correlated_symbol} (${s.most_correlated_value.toFixed(2)})`
                : '—',
          }))}
          columns={symbolCorrelationColumns}
          density="compact"
          disableRowSelectionOnClick
          slots={{ toolbar: GridToolbar }}
          slotProps={{
            toolbar: {
              showQuickFilter: true,
              quickFilterProps: { debounceMs: 300 },
            },
          }}
          initialState={{
            sorting: {
              sortModel: [
                {
                  field: 'weightDisplay',
                  sort: 'desc',
                },
              ],
            },
            pagination: {
              paginationModel: { pageSize: 10 },
            },
          }}
          pageSizeOptions={[10, 25, 50]}
        />
      </Box>
    </Paper>
  )
}

const symbolCorrelationColumns: GridColDef[] = [
  {
    field: 'symbol',
    headerName: 'Symbol',
    flex: 1,
    minWidth: 110,
  },
  {
    field: 'role',
    headerName: 'Role',
    width: 120,
  },
  {
    field: 'cluster',
    headerName: 'Cluster',
    width: 100,
  },
  {
    field: 'weightDisplay',
    headerName: 'Weight',
    width: 120,
  },
  {
    field: 'avgCorrDisplay',
    headerName: 'Avg corr',
    width: 110,
  },
  {
    field: 'mostCorrelatedDisplay',
    headerName: 'Most correlated with',
    flex: 1.2,
    minWidth: 180,
  },
]

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
