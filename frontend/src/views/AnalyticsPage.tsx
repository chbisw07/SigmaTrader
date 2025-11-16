import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import {
  fetchAnalyticsSummary,
  rebuildAnalyticsTrades,
  type AnalyticsSummary,
} from '../services/analytics'

export function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rebuilding, setRebuilding] = useState(false)

  const load = async () => {
    try {
      setLoading(true)
      const data = await fetchAnalyticsSummary(null)
      setSummary(data)
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to load analytics',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleRebuild = async () => {
    setRebuilding(true)
    try {
      await rebuildAnalyticsTrades()
      await load()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to rebuild analytics trades',
      )
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
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 3,
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Typography color="text.secondary">
          Strategy-level P&amp;L and basic performance metrics. Use Rebuild to
          re-generate trades from executed orders.
        </Typography>
        <Button
          size="small"
          variant="outlined"
          onClick={handleRebuild}
          disabled={loading || rebuilding}
        >
          {rebuilding ? 'Rebuilding…' : 'Rebuild trades'}
        </Button>
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
      ) : summary ? (
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
              {summary.avg_loss != null ? summary.avg_loss.toFixed(2) : '-'}
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
    </Box>
  )
}
