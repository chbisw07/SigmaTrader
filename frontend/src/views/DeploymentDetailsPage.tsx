import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import PauseIcon from '@mui/icons-material/Pause'
import StopIcon from '@mui/icons-material/Stop'
import BoltIcon from '@mui/icons-material/Bolt'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import strategyDeploymentHelpText from '../../../docs/strategy_deployment.md?raw'
import { KeyValueJsonDialog } from '../components/KeyValueJsonDialog'
import { MarkdownLite } from '../components/MarkdownLite'
import {
  getDeployment,
  getDeploymentJobsMetrics,
  listDeploymentActions,
  pauseDeployment,
  runDeploymentNow,
  resumeDeployment,
  startDeployment,
  stopDeployment,
  type DeploymentAction,
  type DeploymentJobsMetrics,
  type StrategyDeployment,
} from '../services/deployments'

function fmtTs(ts?: string | null): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleString()
  } catch {
    return ts
  }
}

function fmtAge(ts?: string | null): string {
  if (!ts) return '—'
  const t = Date.parse(ts)
  if (!Number.isFinite(t)) return '—'
  const ms = Date.now() - t
  if (!Number.isFinite(ms)) return '—'
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m`
  const h = Math.floor(min / 60)
  return `${h}h`
}

function statusColor(status: string): 'default' | 'success' | 'warning' | 'error' {
  const s = (status || '').toUpperCase()
  if (s === 'RUNNING') return 'success'
  if (s === 'PAUSED') return 'warning'
  if (s === 'ERROR') return 'error'
  return 'default'
}

function cfgStr(dep: StrategyDeployment | null, key: string): string {
  const cfg = ((dep?.config ?? {}) as Record<string, unknown>) || {}
  const v = cfg[key]
  return typeof v === 'string' ? v : ''
}

export function DeploymentDetailsPage() {
  const { id } = useParams()
  const deploymentId = Number(id)
  const navigate = useNavigate()

  const [deployment, setDeployment] = useState<StrategyDeployment | null>(null)
  const [actions, setActions] = useState<DeploymentAction[]>([])
  const [metrics, setMetrics] = useState<DeploymentJobsMetrics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [actionDialogOpen, setActionDialogOpen] = useState(false)
  const [selectedAction, setSelectedAction] = useState<DeploymentAction | null>(null)
  const [runNowMsg, setRunNowMsg] = useState<string | null>(null)
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false)
  const [pauseReason, setPauseReason] = useState('')

  const refresh = useCallback(async () => {
    if (!Number.isFinite(deploymentId) || deploymentId <= 0) return
    setError(null)
    setLoading(true)
    try {
      const [dep, acts, m] = await Promise.all([
        getDeployment(deploymentId),
        listDeploymentActions(deploymentId, 50),
        getDeploymentJobsMetrics(deploymentId),
      ])
      setDeployment(dep)
      setActions(acts)
      setMetrics(m)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load deployment')
    } finally {
      setLoading(false)
    }
  }, [deploymentId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const status = String(deployment?.state?.status ?? '').toUpperCase()
  const running = status === 'RUNNING'
  const paused = status === 'PAUSED'

  const positions = useMemo(() => {
    return (deployment?.state_summary?.positions ?? []) as Array<Record<string, unknown>>
  }, [deployment?.state_summary?.positions])

  const positionsColumns = useMemo((): GridColDef[] => {
    return [
      {
        field: 'key',
        headerName: 'Symbol',
        width: 180,
        valueGetter: (_value, row) => String((row as any).key ?? '—'),
      },
      {
        field: 'qty',
        headerName: 'Qty',
        width: 90,
        valueGetter: (_value, row) => Number((row as any).qty ?? 0),
      },
      { field: 'side', headerName: 'Side', width: 90 },
      {
        field: 'entry_price',
        headerName: 'Entry',
        width: 110,
        valueGetter: (_value, row) => Number((row as any).entry_price ?? 0),
      },
      {
        field: 'entry_ts',
        headerName: 'Entry Time',
        width: 190,
        valueGetter: (_value, row) => String((row as any).entry_ts ?? ''),
        renderCell: (p) => <>{fmtTs(String(p.value ?? ''))}</>,
      },
      {
        field: 'peak',
        headerName: 'Peak',
        width: 110,
        valueGetter: (_value, row) => Number((row as any).peak ?? 0),
      },
      {
        field: 'trough',
        headerName: 'Trough',
        width: 110,
        valueGetter: (_value, row) => Number((row as any).trough ?? 0),
      },
      {
        field: 'holding_bars',
        headerName: 'Bars',
        width: 90,
        valueGetter: (_value, row) => Number((row as any).holding_bars ?? 0),
      },
      {
        field: 'disaster_stop_order_id',
        headerName: 'Stop Order',
        width: 120,
        valueGetter: (_value, row) => (row as any).disaster_stop_order_id ?? '—',
      },
    ]
  }, [])

  const actionColumns = useMemo((): GridColDef[] => {
    const get = (row: DeploymentAction, key: string): unknown => (row.payload ?? {})[key]
    const getListLen = (row: DeploymentAction, key: string): number => {
      const v = get(row, key)
      return Array.isArray(v) ? v.length : 0
    }
    return [
      { field: 'id', headerName: 'ID', width: 80 },
      {
        field: 'created_at',
        headerName: 'When',
        width: 190,
        valueGetter: (_value, row) => String((row as DeploymentAction).created_at ?? ''),
        renderCell: (p) => <>{fmtTs(String(p.value ?? ''))}</>,
      },
      { field: 'kind', headerName: 'Kind', width: 140 },
      {
        field: 'job_kind',
        headerName: 'Job',
        width: 160,
        valueGetter: (_value, row) =>
          String((row as DeploymentAction).payload?.job_kind ?? '—'),
      },
      {
        field: 'open_positions',
        headerName: 'Open',
        width: 90,
        valueGetter: (_value, row) =>
          Number((row as DeploymentAction).payload?.open_positions ?? 0),
      },
      {
        field: 'orders',
        headerName: 'Orders',
        width: 90,
        valueGetter: (_value, row) => getListLen(row as DeploymentAction, 'orders'),
      },
      {
        field: 'events',
        headerName: 'Events',
        width: 90,
        valueGetter: (_value, row) => getListLen(row as DeploymentAction, 'events'),
      },
      {
        field: 'age',
        headerName: 'Age',
        width: 90,
        valueGetter: (_value, row) => String((row as DeploymentAction).created_at ?? ''),
        renderCell: (p) => <>{fmtAge(String(p.value ?? ''))}</>,
      },
    ]
  }, [])

  const lastEvalDslEntry =
    (actions[0]?.payload?.dsl as Record<string, unknown> | undefined)?.entry ??
    cfgStr(deployment, 'entry_dsl')
  const lastEvalDslExit =
    (actions[0]?.payload?.dsl as Record<string, unknown> | undefined)?.exit ??
    cfgStr(deployment, 'exit_dsl')

  return (
    <Box sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="Back to deployments">
            <IconButton onClick={() => navigate('/deployments')} size="small">
              <ArrowBackIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Typography variant="h6" sx={{ flex: 1, minWidth: 0 }} noWrap>
            Deployment #{deploymentId}{deployment?.name ? ` — ${deployment.name}` : ''}
          </Typography>
          <Tooltip title="Help">
            <IconButton size="small" onClick={() => setHelpOpen(true)}>
              <HelpOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Chip
            size="small"
            label={String(deployment?.state?.status ?? '—')}
            color={statusColor(String(deployment?.state?.status ?? ''))}
            variant={
              statusColor(String(deployment?.state?.status ?? '')) === 'default'
                ? 'outlined'
                : 'filled'
            }
          />
          {running ? (
            <Button
              size="small"
              startIcon={<PauseIcon />}
              variant="outlined"
              onClick={() => {
                if (!deployment) return
                setPauseReason(deployment.state?.pause_reason ?? '')
                setPauseDialogOpen(true)
              }}
              disabled={!deployment || loading}
            >
              Pause
            </Button>
          ) : paused ? (
            <Button
              size="small"
              startIcon={<PlayArrowIcon />}
              variant="outlined"
              onClick={() => {
                if (!deployment) return
                void (async () => {
                  try {
                    await resumeDeployment(deployment.id)
                    await refresh()
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Failed to resume')
                  }
                })()
              }}
              disabled={!deployment || loading}
            >
              Resume
            </Button>
          ) : (
            <Button
              size="small"
              startIcon={<PlayArrowIcon />}
              variant="outlined"
              onClick={() => {
                if (!deployment) return
                void (async () => {
                  try {
                    await startDeployment(deployment.id)
                    await refresh()
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Failed to start')
                  }
                })()
              }}
              disabled={!deployment || loading}
            >
              Start
            </Button>
          )}
          <Button
            size="small"
            startIcon={<StopIcon />}
            variant="outlined"
            onClick={() => {
              if (!deployment) return
              void (async () => {
                try {
                  await stopDeployment(deployment.id)
                  await refresh()
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed to stop')
                }
              })()
            }}
            disabled={!deployment || loading || (!running && !paused)}
          >
            Stop
          </Button>
          <Tooltip title={paused ? 'Resume before running now.' : 'Enqueue an evaluation job immediately.'}>
            <span>
              <Button
                size="small"
                startIcon={<BoltIcon />}
                variant="contained"
                onClick={() => {
                  if (!deployment) return
                  void (async () => {
                    setRunNowMsg(null)
                    try {
                      const res = await runDeploymentNow(deployment.id)
                      const when = res.scheduled_for ? fmtTs(String(res.scheduled_for)) : '—'
                      setRunNowMsg(
                        res.enqueued
                          ? `Enqueued evaluation job for ${when}`
                          : 'Job already queued for this bar (deduped).',
                      )
                      await refresh()
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Failed to enqueue')
                    }
                  })()
                }}
                disabled={!deployment || loading || paused}
              >
                Run now
              </Button>
            </span>
          </Tooltip>
          <Button
            size="small"
            startIcon={<RefreshIcon />}
            variant="outlined"
            onClick={() => void refresh()}
            disabled={loading}
          >
            Refresh
          </Button>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}
        {runNowMsg ? <Alert severity="success">{runNowMsg}</Alert> : null}
        {paused ? (
          <Alert
            severity="warning"
            action={
              <Tooltip title="While paused, evaluations stop but broker-side protections and MIS square-off remain active.">
                <IconButton size="small">
                  <HelpOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            }
          >
            Paused
            {deployment?.state?.paused_at ? ` at ${fmtTs(deployment.state.paused_at)}` : ''}
            {deployment?.state?.pause_reason ? ` — ${deployment.state.pause_reason}` : ''}
          </Alert>
        ) : null}

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1">Status</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap">
              <Chip
                label={`Last eval: ${fmtTs(deployment?.state?.last_evaluated_at ?? null)}`}
                variant="outlined"
              />
              <Chip
                label={`Next eval: ${fmtTs(deployment?.state?.next_evaluate_at ?? null)}`}
                variant="outlined"
              />
              <Chip
                label={`Open positions: ${deployment?.state_summary?.open_positions ?? 0}`}
                variant="outlined"
              />
              {paused ? (
                <Chip
                  label={`Paused at: ${fmtTs(deployment?.state?.paused_at ?? null)}`}
                  variant="outlined"
                />
              ) : null}
              {metrics?.oldest_pending_scheduled_for ? (
                <Chip
                  label={`Oldest pending: ${fmtTs(metrics.oldest_pending_scheduled_for)} (${fmtAge(metrics.oldest_pending_scheduled_for)})`}
                  color="warning"
                  variant="outlined"
                />
              ) : (
                <Chip label="Oldest pending: —" variant="outlined" />
              )}
              {metrics?.latest_failed_updated_at ? (
                <Chip
                  label={`Latest failure: ${fmtTs(metrics.latest_failed_updated_at)} (${fmtAge(metrics.latest_failed_updated_at)})`}
                  color="error"
                  variant="outlined"
                />
              ) : (
                <Chip label="Latest failure: —" variant="outlined" />
              )}
            </Stack>

            {deployment?.state?.last_error ? (
              <Alert severity="error">Last error: {deployment.state.last_error}</Alert>
            ) : null}

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label="Entry DSL (last eval snapshot)"
                value={String(lastEvalDslEntry ?? '')}
                fullWidth
                multiline
                minRows={2}
                InputProps={{ readOnly: true }}
              />
              <TextField
                label="Exit DSL (last eval snapshot)"
                value={String(lastEvalDslExit ?? '')}
                fullWidth
                multiline
                minRows={2}
                InputProps={{ readOnly: true }}
              />
            </Stack>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Typography variant="subtitle1">Positions</Typography>
            <Box sx={{ height: 320 }}>
              <DataGrid
                rows={positions.map((p, idx) => ({ id: String((p as any).key ?? idx), ...p }))}
                columns={positionsColumns}
                density="compact"
                disableRowSelectionOnClick
                hideFooter
              />
            </Box>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Typography variant="subtitle1">Recent actions</Typography>
            <Box sx={{ height: 360 }}>
              <DataGrid
                rows={actions}
                columns={actionColumns}
                getRowId={(r) => (r as DeploymentAction).id}
                density="compact"
                disableRowSelectionOnClick
                onRowClick={(p) => {
                  const row = p.row as DeploymentAction
                  setSelectedAction(row)
                  setActionDialogOpen(true)
                }}
              />
            </Box>
            <Typography variant="body2" color="text.secondary">
              Click a row to inspect the full action payload (evaluation summary).
            </Typography>
          </Stack>
        </Paper>
      </Stack>

      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Strategy deployment help</DialogTitle>
        <DialogContent>
          <MarkdownLite text={strategyDeploymentHelpText} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={pauseDialogOpen}
        onClose={() => setPauseDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Pause deployment</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Pausing stops strategy evaluations and new entries/exits, but any broker-side
              protections (like disaster stop/GTT) and MIS square-off remain active.
            </Typography>
            <TextField
              label="Reason (optional)"
              value={pauseReason}
              onChange={(e) => setPauseReason(e.target.value)}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPauseDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (!deployment) return
              void (async () => {
                try {
                  await pauseDeployment(deployment.id, pauseReason)
                  setPauseDialogOpen(false)
                  await refresh()
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed to pause')
                }
              })()
            }}
          >
            Pause
          </Button>
        </DialogActions>
      </Dialog>

      <KeyValueJsonDialog
        open={actionDialogOpen && selectedAction != null}
        onClose={() => {
          setActionDialogOpen(false)
          setSelectedAction(null)
        }}
        title={`Deployment action #${selectedAction?.id ?? ''}`}
        value={selectedAction ?? {}}
      />
    </Box>
  )
}
