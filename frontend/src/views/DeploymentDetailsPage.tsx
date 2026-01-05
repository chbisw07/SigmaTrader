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
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
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
  resolveDirectionMismatch,
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
  const [mismatchResolveDialogOpen, setMismatchResolveDialogOpen] = useState(false)
  const [mismatchResolveAction, setMismatchResolveAction] = useState<
    'ADOPT_EXIT_ONLY' | 'FLATTEN_THEN_CONTINUE' | null
  >(null)
  const [startConfirmOpen, setStartConfirmOpen] = useState(false)
  const [startConfirmMode, setStartConfirmMode] = useState<'START' | 'RESUME'>('START')
  const [startConfirmAckShort, setStartConfirmAckShort] = useState(false)
  const [startConfirmAckEnter, setStartConfirmAckEnter] = useState(false)
  const [exposureWarnOpen, setExposureWarnOpen] = useState(false)

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
  const runtimeState = String(deployment?.state?.runtime_state ?? '').toUpperCase()
  const exposureSymbols = (deployment?.state?.exposure?.symbols ??
    []) as Array<Record<string, unknown>>
  const hasBrokerExposure = exposureSymbols.some(
    (s) => Number(s.broker_net_qty ?? 0) !== 0,
  )
  const hasDirectionMismatch = paused && runtimeState === 'PAUSED_DIRECTION_MISMATCH'

  const runStartOrResume = useCallback(
    async (mode: 'START' | 'RESUME') => {
      if (!deployment) return
      const dir = String((deployment.config ?? {}).direction ?? '').toUpperCase()
      const enterOnStart = Boolean((deployment.config ?? {}).enter_immediately_on_start)
      const needsShort = dir === 'SHORT'
      const needsEnter = enterOnStart
      if (needsShort || needsEnter) {
        setStartConfirmMode(mode)
        setStartConfirmAckShort(false)
        setStartConfirmAckEnter(false)
        setStartConfirmOpen(true)
        return
      }
      try {
        const res =
          mode === 'RESUME'
            ? await resumeDeployment(deployment.id)
            : await startDeployment(deployment.id)
        setDeployment(res)
        const symbols = (res.state?.exposure?.symbols ?? []) as any[]
        const hasExposure = symbols.some((s) => Number(s?.broker_net_qty ?? 0) !== 0)
        if (hasExposure) setExposureWarnOpen(true)
        await refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed')
      }
    },
    [deployment, refresh],
  )

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
                void runStartOrResume('RESUME')
              }}
              disabled={!deployment || loading || hasDirectionMismatch}
            >
              Resume
            </Button>
          ) : (
            <Button
              size="small"
              startIcon={<PlayArrowIcon />}
              variant="outlined"
              onClick={() => {
                void runStartOrResume('START')
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
        {hasBrokerExposure ? (
          <Alert severity="warning">
            <Stack spacing={0.5}>
              <Typography variant="body2">
                Existing broker exposure detected. Review before running to avoid duplicate
                trades and unexpected losses.
              </Typography>
              <Stack spacing={0} sx={{ pl: 0.5 }}>
                {exposureSymbols
                  .filter((s) => Number(s.broker_net_qty ?? 0) !== 0)
                  .slice(0, 6)
                  .map((s, idx) => (
                    <Typography
                      key={String(s.symbol ?? idx)}
                      variant="body2"
                      color="text.secondary"
                    >
                      {String(s.exchange ?? '—')}:{String(s.symbol ?? '—')} — broker{' '}
                      {String(s.broker_net_qty ?? 0)} ({String(s.broker_side ?? '—')})
                      {Number(s.deployments_net_qty ?? 0) !== 0
                        ? `; deployments ${String(s.deployments_net_qty ?? 0)}`
                        : ''}
                    </Typography>
                  ))}
              </Stack>
            </Stack>
          </Alert>
        ) : null}
        {hasDirectionMismatch ? (
          <Alert severity="error">
            <Stack spacing={1}>
              <Typography variant="body2">
                Direction mismatch detected with existing broker position(s). Resolve this
                before resuming.
              </Typography>
              <Box sx={{ overflowX: 'auto' }}>
                <Box component="table" sx={{ width: '100%', borderSpacing: 0 }}>
                  <Box component="thead">
                    <Box component="tr">
                      <Box component="th" sx={{ textAlign: 'left', pr: 2 }}>
                        Symbol
                      </Box>
                      <Box component="th" sx={{ textAlign: 'left', pr: 2 }}>
                        Broker Qty
                      </Box>
                      <Box component="th" sx={{ textAlign: 'left', pr: 2 }}>
                        Broker Side
                      </Box>
                    </Box>
                  </Box>
                  <Box component="tbody">
                    {exposureSymbols
                      .filter((s) => Number(s.broker_net_qty ?? 0) !== 0)
                      .map((s, idx) => (
                        <Box component="tr" key={String(s.symbol ?? idx)}>
                          <Box component="td" sx={{ pr: 2 }}>
                            {String(s.exchange ?? '—')}:{String(s.symbol ?? '—')}
                          </Box>
                          <Box component="td" sx={{ pr: 2 }}>
                            {String(s.broker_net_qty ?? 0)}
                          </Box>
                          <Box component="td" sx={{ pr: 2 }}>
                            {String(s.broker_side ?? '—')}
                          </Box>
                        </Box>
                      ))}
                  </Box>
                </Box>
              </Box>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                <Button
                  size="small"
                  variant="contained"
                  onClick={() => {
                    setMismatchResolveAction('ADOPT_EXIT_ONLY')
                    setMismatchResolveDialogOpen(true)
                  }}
                >
                  Adopt (exit-only)
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  color="warning"
                  onClick={() => {
                    setMismatchResolveAction('FLATTEN_THEN_CONTINUE')
                    setMismatchResolveDialogOpen(true)
                  }}
                >
                  Flatten then resume
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    if (!deployment) return
                    void (async () => {
                      try {
                        await resolveDirectionMismatch(deployment.id, 'IGNORE')
                        await refresh()
                      } catch (err) {
                        setError(
                          err instanceof Error ? err.message : 'Failed to keep paused',
                        )
                      }
                    })()
                  }}
                >
                  Keep paused
                </Button>
              </Stack>
            </Stack>
          </Alert>
        ) : null}
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

      <Dialog
        open={mismatchResolveDialogOpen}
        onClose={() => setMismatchResolveDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Resolve direction mismatch</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              This can have negative consequences (including losses). Proceed only if you
              understand the implication.
            </Typography>
            <Typography variant="body2">
              Action: {mismatchResolveAction ?? '—'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Adopt (exit-only) imports the existing broker position into this deployment
              and only allows exits. Flatten then resume enqueues an immediate flatten
              order and resumes normal operation afterwards.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMismatchResolveDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (!deployment || !mismatchResolveAction) return
              void (async () => {
                try {
                  await resolveDirectionMismatch(deployment.id, mismatchResolveAction)
                  setMismatchResolveDialogOpen(false)
                  setMismatchResolveAction(null)
                  await refresh()
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed to resolve')
                }
              })()
            }}
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={startConfirmOpen}
        onClose={() => setStartConfirmOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{startConfirmMode === 'RESUME' ? 'Resume' : 'Start'} deployment</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Trading actions can have negative consequences (including losses). Confirm to
              proceed.
            </Typography>
            {String((deployment?.config ?? {}).direction ?? '').toUpperCase() === 'SHORT' ? (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={startConfirmAckShort}
                    onChange={(e) => setStartConfirmAckShort(e.target.checked)}
                  />
                }
                label="I understand short-selling risks and accept responsibility."
              />
            ) : null}
            {Boolean((deployment?.config ?? {}).enter_immediately_on_start) ? (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={startConfirmAckEnter}
                    onChange={(e) => setStartConfirmAckEnter(e.target.checked)}
                  />
                }
                label="I understand “enter immediately on start” can trigger trades quickly."
              />
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStartConfirmOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              (String((deployment?.config ?? {}).direction ?? '').toUpperCase() ===
                'SHORT' &&
                !startConfirmAckShort) ||
              (Boolean((deployment?.config ?? {}).enter_immediately_on_start) &&
                !startConfirmAckEnter)
            }
            onClick={() => {
              if (!deployment) return
              void (async () => {
                try {
                  const res =
                    startConfirmMode === 'RESUME'
                      ? await resumeDeployment(deployment.id)
                      : await startDeployment(deployment.id)
                  setDeployment(res)
                  setStartConfirmOpen(false)
                  const symbols = (res.state?.exposure?.symbols ?? []) as any[]
                  const hasExposure = symbols.some((s) => Number(s?.broker_net_qty ?? 0) !== 0)
                  if (hasExposure) setExposureWarnOpen(true)
                  await refresh()
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed')
                }
              })()
            }}
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={exposureWarnOpen} onClose={() => setExposureWarnOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Existing exposure detected</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Existing broker positions were detected. Running this deployment may place
              duplicate orders or increase exposure.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExposureWarnOpen(false)}>Keep running</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => {
              if (!deployment) return
              void (async () => {
                try {
                  await pauseDeployment(deployment.id, 'Paused after exposure warning.')
                  setExposureWarnOpen(false)
                  await refresh()
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed to pause')
                }
              })()
            }}
          >
            Pause now
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
