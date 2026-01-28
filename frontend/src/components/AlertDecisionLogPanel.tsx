import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { fetchAlertDecisionLog, type AlertDecisionLogRow } from '../services/riskEngine'

export function AlertDecisionLogPanel({
  title = 'Alert decision log',
  helpHash = 'alert-decision-log-v2',
  limit = 200,
}: {
  title?: string
  helpHash?: string | null
  limit?: number
}) {
  const navigate = useNavigate()
  const [rows, setRows] = useState<AlertDecisionLogRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setBusy(true)
    try {
      const res = await fetchAlertDecisionLog(limit)
      setRows(Array.isArray(res) ? res : [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load decision log')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 260 }}>
          {title}
        </Typography>
        {helpHash ? (
          <Tooltip title="Help" arrow placement="top">
            <IconButton
              size="small"
              onClick={() => navigate(`/risk-guide#${helpHash}`)}
              aria-label="decision log help"
            >
              <HelpOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        ) : null}
        <Tooltip title="Refresh" arrow placement="top">
          <span>
            <IconButton size="small" onClick={() => void load()} disabled={busy}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        {busy ? <CircularProgress size={18} /> : null}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        Shows resolved product/profile/category and whether the order was placed or blocked.
      </Typography>
      <Divider sx={{ my: 2 }} />
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Time</TableCell>
            <TableCell>Symbol</TableCell>
            <TableCell>Strategy</TableCell>
            <TableCell>Hint</TableCell>
            <TableCell>Resolved</TableCell>
            <TableCell>Category</TableCell>
            <TableCell>DD%</TableCell>
            <TableCell>State</TableCell>
            <TableCell>Decision</TableCell>
            <TableCell>Reasons</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.id}>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>
                {new Date(r.created_at).toLocaleString()}
              </TableCell>
              <TableCell>{r.symbol ?? '—'}</TableCell>
              <TableCell>{r.strategy_ref ?? '—'}</TableCell>
              <TableCell>{r.product_hint ?? '—'}</TableCell>
              <TableCell>{r.resolved_product ?? '—'}</TableCell>
              <TableCell>{r.risk_category ?? '—'}</TableCell>
              <TableCell>
                {r.drawdown_pct != null ? Number(r.drawdown_pct).toFixed(2) : '—'}
              </TableCell>
              <TableCell>{r.drawdown_state ?? '—'}</TableCell>
              <TableCell>
                <Chip
                  size="small"
                  label={r.decision}
                  color={
                    r.decision === 'PLACED'
                      ? 'success'
                      : r.decision === 'BLOCKED'
                        ? 'error'
                        : 'default'
                  }
                  variant={r.decision === 'PLACED' ? 'filled' : 'outlined'}
                />
              </TableCell>
              <TableCell sx={{ maxWidth: 360 }}>
                <Typography variant="caption" color="text.secondary">
                  {r.reasons_json}
                </Typography>
              </TableCell>
            </TableRow>
          ))}
          {rows.length === 0 && !busy && (
            <TableRow>
              <TableCell colSpan={10}>
                <Typography variant="caption" color="text.secondary">
                  No decision logs yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {error ? (
        <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
          {error}
        </Typography>
      ) : null}
    </Paper>
  )
}

