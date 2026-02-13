import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
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
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { fetchAlertDecisionLogFiltered, type AlertDecisionLogRow } from '../services/riskEngine'

const formatDateLocal = (d: Date): string => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const dateRangeToIso = (range: { from: string; to: string }): { fromIso?: string; toIso?: string } => {
  const from = (range.from || '').trim()
  const to = (range.to || '').trim()
  if (!from && !to) return {}
  const out: { fromIso?: string; toIso?: string } = {}
  if (from) out.fromIso = new Date(`${from}T00:00:00`).toISOString()
  if (to) out.toIso = new Date(`${to}T23:59:59.999`).toISOString()
  return out
}

function formatReasons(raw: string | null | undefined): string {
  const s = (raw ?? '').trim()
  if (!s) return ''

  try {
    const parsed = JSON.parse(s) as unknown
    if (Array.isArray(parsed)) {
      const items = parsed
        .map((v) => {
          if (v == null) return ''
          if (typeof v === 'string') return v.trim()
          return JSON.stringify(v)
        })
        .filter(Boolean)
      return items.length ? items.join('; ') : ''
    }
  } catch {
    // best-effort: treat as plain text
  }

  // Fallback for strings like: ["a","b"]
  if (s.startsWith('[') && s.endsWith(']')) {
    const inner = s.slice(1, -1).trim()
    if (!inner) return ''
    return inner.replaceAll(/^"|"$/g, '').replaceAll('","', '; ')
  }

  return s
}

export function AlertDecisionLogPanel({
  title = 'Alert decision log',
  helpHash = 'alert-decision-log',
  limit = 200,
  active = true,
}: {
  title?: string
  helpHash?: string | null
  limit?: number
  active?: boolean
}) {
  const navigate = useNavigate()
  const today = formatDateLocal(new Date())
  const [rows, setRows] = useState<AlertDecisionLogRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rangeDraft, setRangeDraft] = useState<{ from: string; to: string }>({
    from: today,
    to: today,
  })
  const [rangeApplied, setRangeApplied] = useState<{ from: string; to: string }>({
    from: today,
    to: today,
  })

  const load = async () => {
    setBusy(true)
    try {
      const { fromIso, toIso } = dateRangeToIso(rangeApplied)
      const res = await fetchAlertDecisionLogFiltered({
        limit,
        createdFrom: fromIso,
        createdTo: toIso,
      })
      setRows(Array.isArray(res) ? res : [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load decision log')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!active) return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, limit, rangeApplied])

  if (!active) return null

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 260 }}>
          {title}
        </Typography>
        <TextField
          size="small"
          label="From"
          type="date"
          value={rangeDraft.from}
          onChange={(e) => setRangeDraft((prev) => ({ ...prev, from: e.target.value }))}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 150 }}
        />
        <TextField
          size="small"
          label="To"
          type="date"
          value={rangeDraft.to}
          onChange={(e) => setRangeDraft((prev) => ({ ...prev, to: e.target.value }))}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 150 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => {
            const a = (rangeDraft.from || '').trim()
            const b = (rangeDraft.to || '').trim()
            if (a && b && a > b) {
              setError('Invalid date range: From must be <= To.')
              return
            }
            // UI guardrail; backend enforces too.
            if (a && b) {
              const days = Math.floor(
                (new Date(`${b}T00:00:00`).getTime() - new Date(`${a}T00:00:00`).getTime()) /
                  (24 * 60 * 60 * 1000),
              ) + 1
              if (days > 15) {
                setError('Date range too large; max allowed is 15 days.')
                return
              }
            }
            setError(null)
            setRangeApplied(rangeDraft)
          }}
          disabled={busy}
        >
          Apply
        </Button>
        <Button
          size="small"
          variant="text"
          onClick={() => {
            const t = formatDateLocal(new Date())
            setError(null)
            setRangeDraft({ from: t, to: t })
            setRangeApplied({ from: t, to: t })
          }}
          disabled={busy}
        >
          Today
        </Button>
        <Button
          size="small"
          variant="text"
          onClick={() => {
            const now = new Date()
            const to = formatDateLocal(now)
            const fromD = new Date(now)
            fromD.setDate(now.getDate() - 6)
            const from = formatDateLocal(fromD)
            setError(null)
            setRangeDraft({ from, to })
            setRangeApplied({ from, to })
          }}
          disabled={busy}
        >
          7D
        </Button>
        <Button
          size="small"
          variant="text"
          onClick={() => {
            const now = new Date()
            const to = formatDateLocal(now)
            const fromD = new Date(now)
            fromD.setDate(now.getDate() - 14)
            const from = formatDateLocal(fromD)
            setError(null)
            setRangeDraft({ from, to })
            setRangeApplied({ from, to })
          }}
          disabled={busy}
        >
          15D
        </Button>
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
                  {formatReasons(r.reasons_json)}
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
