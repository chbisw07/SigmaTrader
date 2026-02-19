import { useEffect, useMemo, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import Chip from '@mui/material/Chip'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'

import {
  attachPlaybookToShadow,
  fetchCoverageShadows,
  syncCoverageFromLatestSnapshot,
  updateManagePlaybook,
  type PositionShadow,
} from '../../services/aiTradingManager'
import { ManagePlaybookModal } from './ManagePlaybookModal'

function fmtNum(v: number | null | undefined, digits = 2) {
  if (v == null || Number.isNaN(v)) return '—'
  return Number(v).toFixed(digits)
}

function fmtInt(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return '—'
  return String(Math.round(Number(v)))
}

export function AiCoveragePanel(props: {
  accountId?: string
  onOpenJournal?: (shadowId: string) => void
}) {
  const accountId = props.accountId ?? 'default'
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unmanagedOnly, setUnmanagedOnly] = useState(true)
  const [rows, setRows] = useState<PositionShadow[]>([])
  const [templateByShadow, setTemplateByShadow] = useState<Record<string, string>>({})
  const [busyByShadow, setBusyByShadow] = useState<Record<string, boolean>>({})
  const [editPlaybookId, setEditPlaybookId] = useState<string | null>(null)

  const templateOptions = useMemo(
    () => [
      { value: 'swing_cnc_atr_ladder', label: 'Swing CNC (ATR + ladder)' },
      { value: 'mis_intraday', label: 'MIS intraday (time stop)' },
      { value: 'longterm', label: 'Long-term (review only)' },
    ],
    [],
  )

  const load = async (opts?: { silent?: boolean }) => {
    try {
      if (!opts?.silent) setLoading(true)
      const data = await fetchCoverageShadows({
        account_id: accountId,
        status_filter: 'OPEN',
        unmanaged_only: unmanagedOnly,
        limit: 500,
      })
      setRows(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load coverage')
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId, unmanagedOnly])

  const handleSync = async () => {
    setSyncing(true)
    try {
      await syncCoverageFromLatestSnapshot({ account_id: accountId })
      await load({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync')
    } finally {
      setSyncing(false)
    }
  }

  const handleAttach = async (shadowId: string) => {
    setBusyByShadow((p) => ({ ...p, [shadowId]: true }))
    try {
      const template = templateByShadow[shadowId] || 'swing_cnc_atr_ladder'
      await attachPlaybookToShadow({ shadow_id: shadowId, template })
      await load({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to attach playbook')
    } finally {
      setBusyByShadow((p) => ({ ...p, [shadowId]: false }))
    }
  }

  const handleToggleManaged = async (shadow: PositionShadow, enabled: boolean) => {
    if (!shadow.playbook_id) return
    setBusyByShadow((p) => ({ ...p, [shadow.shadow_id]: true }))
    try {
      await updateManagePlaybook({ playbook_id: shadow.playbook_id, patch: { enabled } })
      await load({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update playbook')
    } finally {
      setBusyByShadow((p) => ({ ...p, [shadow.shadow_id]: false }))
    }
  }

  return (
    <Box sx={{ px: 2, pt: 1, pb: 2 }}>
      <ManagePlaybookModal
        open={Boolean(editPlaybookId)}
        playbookId={editPlaybookId || ''}
        onClose={() => setEditPlaybookId(null)}
        onSaved={() => void load({ silent: true })}
      />
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap">
        <Box>
          <Typography variant="h6">Coverage</Typography>
          <Typography variant="caption" color="text.secondary">
            Broker-truth holdings/positions detected from snapshots. Attach a playbook to make a position “managed”.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={unmanagedOnly}
                onChange={(e) => setUnmanagedOnly(e.target.checked)}
              />
            }
            label="Unmanaged only"
          />
          <Button variant="outlined" size="small" onClick={() => void load()} disabled={loading || syncing}>
            Refresh
          </Button>
          <Button variant="contained" size="small" onClick={handleSync} disabled={syncing}>
            {syncing ? 'Syncing…' : 'Sync now'}
          </Button>
        </Stack>
      </Stack>

      {error ? (
        <Paper variant="outlined" sx={{ mt: 1, p: 1, borderColor: 'error.main' }}>
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        </Paper>
      ) : null}

      <Divider sx={{ my: 1 }} />

      {loading ? (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
          <CircularProgress size={18} />
          <Typography variant="body2">Loading…</Typography>
        </Stack>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell>Product</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Avg</TableCell>
                <TableCell align="right">LTP</TableCell>
                <TableCell align="right">P&amp;L</TableCell>
                <TableCell>Managed</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => {
                const busy = Boolean(busyByShadow[r.shadow_id])
                const managed = Boolean(r.managed)
                const pnlTxt = r.pnl_abs == null ? '—' : `${fmtNum(r.pnl_abs, 2)} (${fmtNum(r.pnl_pct, 2)}%)`
                return (
                  <TableRow key={r.shadow_id} hover>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {r.symbol}
                        </Typography>
                        {r.source && r.source !== 'ST' ? (
                          <Chip size="small" label={r.source} variant="outlined" />
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell>{r.product}</TableCell>
                    <TableCell align="right">{fmtInt(r.qty_current)}</TableCell>
                    <TableCell align="right">{fmtNum(r.avg_price, 2)}</TableCell>
                    <TableCell align="right">{fmtNum(r.ltp, 2)}</TableCell>
                    <TableCell align="right">{pnlTxt}</TableCell>
                    <TableCell>
                      {r.playbook_id ? (
                        <Chip
                          size="small"
                          color={managed ? 'success' : 'default'}
                          label={managed ? `ON • ${r.playbook_mode || 'OBSERVE'}` : 'OFF'}
                        />
                      ) : (
                        <Chip size="small" color="warning" label="UNMANAGED" />
                      )}
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                        {r.playbook_id ? (
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={busy}
                            onClick={() => void handleToggleManaged(r, !managed)}
                          >
                            {managed ? 'Disable' : 'Enable'}
                          </Button>
                        ) : (
                          <>
                            <Select
                              size="small"
                              value={templateByShadow[r.shadow_id] || 'swing_cnc_atr_ladder'}
                              onChange={(e) =>
                                setTemplateByShadow((p) => ({ ...p, [r.shadow_id]: String(e.target.value) }))
                              }
                              sx={{ minWidth: 210 }}
                            >
                              {templateOptions.map((opt) => (
                                <MenuItem key={opt.value} value={opt.value}>
                                  {opt.label}
                                </MenuItem>
                              ))}
                            </Select>
                            <Button size="small" variant="contained" disabled={busy} onClick={() => void handleAttach(r.shadow_id)}>
                              Attach
                            </Button>
                          </>
                        )}
                        {r.playbook_id ? (
                          <Button size="small" variant="text" onClick={() => setEditPlaybookId(r.playbook_id as string)} disabled={busy}>
                            Edit
                          </Button>
                        ) : null}
                        <Button
                          size="small"
                          variant="text"
                          onClick={() => props.onOpenJournal?.(r.shadow_id)}
                        >
                          Journal
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
              {!rows.length ? (
                <TableRow>
                  <TableCell colSpan={8}>
                    <Typography variant="body2" color="text.secondary">
                      No rows.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}
