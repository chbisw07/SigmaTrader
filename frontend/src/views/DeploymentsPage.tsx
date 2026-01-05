import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import AddIcon from '@mui/icons-material/Add'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import PauseIcon from '@mui/icons-material/Pause'
import StopIcon from '@mui/icons-material/Stop'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import Autocomplete from '@mui/material/Autocomplete'
import IconButton from '@mui/material/IconButton'
import Chip from '@mui/material/Chip'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'

import strategyDeploymentHelpText from '../../../docs/strategy_deployment.md?raw'
import { MarkdownLite } from '../components/MarkdownLite'
import {
  createDeployment,
  deleteDeployment,
  listDeployments,
  pauseDeployment,
  resumeDeployment,
  startDeployment,
  stopDeployment,
  updateDeployment,
  type DeploymentKind,
  type DeploymentUniverse,
  type StrategyDeployment,
} from '../services/deployments'
import { listGroups } from '../services/groups'
import { searchMarketSymbols, type MarketSymbol } from '../services/marketData'

type DeploymentPrefill = {
  kind: DeploymentKind
  universe: DeploymentUniverse
  config: Record<string, unknown>
}

type LocationState = {
  deploymentPrefill?: DeploymentPrefill
}

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

function statusColor(
  status: string,
): 'default' | 'success' | 'warning' | 'error' {
  const s = (status || '').toUpperCase()
  if (s === 'RUNNING') return 'success'
  if (s === 'PAUSED') return 'warning'
  if (s === 'ERROR') return 'error'
  return 'default'
}

type EditorState = {
  id?: number
  name: string
  description: string
  kind: DeploymentKind
  target_kind: 'SYMBOL' | 'GROUP'
  exchange: string
  symbol: string
  group_id: number | ''
  timeframe: string
  broker_name: 'zerodha' | 'angelone'
  execution_target: 'PAPER' | 'LIVE'
  product: 'CNC' | 'MIS'
  direction: 'LONG' | 'SHORT'
  acknowledge_short_risk: boolean
  enter_immediately_on_start: boolean
  acknowledge_enter_immediately_risk: boolean
  entry_dsl: string
  exit_dsl: string
  initial_cash: number
  position_size_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  trailing_stop_pct: number
  max_open_positions: number
  allocation_mode: 'EQUAL' | 'RANKING'
  ranking_window: number
  sizing_mode: 'PCT_EQUITY' | 'FIXED_CASH' | 'CASH_PER_SLOT'
  fixed_cash_per_trade: number
  min_holding_bars: number
  cooldown_bars: number
  max_equity_dd_global_pct: number
  max_equity_dd_trade_pct: number
  daily_via_intraday_enabled: boolean
  base_timeframe: '1m' | '5m' | '15m' | '30m' | '1h'
  proxy_close_hhmm: string
}

function defaultEditorState(): EditorState {
  return {
    name: '',
    description: '',
    kind: 'STRATEGY',
    target_kind: 'SYMBOL',
    exchange: 'NSE',
    symbol: '',
    group_id: '',
    timeframe: '1m',
    broker_name: 'zerodha',
    execution_target: 'PAPER',
    product: 'CNC',
    direction: 'LONG',
    acknowledge_short_risk: false,
    enter_immediately_on_start: false,
    acknowledge_enter_immediately_risk: false,
    entry_dsl: 'PRICE(1d) > SMA(20,1d)',
    exit_dsl: 'PRICE(1d) < SMA(20,1d)',
    initial_cash: 100000,
    position_size_pct: 100,
    stop_loss_pct: 0,
    take_profit_pct: 0,
    trailing_stop_pct: 0,
    max_open_positions: 10,
    allocation_mode: 'EQUAL',
    ranking_window: 5,
    sizing_mode: 'PCT_EQUITY',
    fixed_cash_per_trade: 0,
    min_holding_bars: 0,
    cooldown_bars: 0,
    max_equity_dd_global_pct: 0,
    max_equity_dd_trade_pct: 0,
    daily_via_intraday_enabled: true,
    base_timeframe: '5m',
    proxy_close_hhmm: '15:25',
  }
}

function editorToPayload(s: EditorState): {
  name: string
  description?: string | null
  kind: DeploymentKind
  enabled: boolean
  universe: DeploymentUniverse
  config: Record<string, unknown>
} {
  const universe: DeploymentUniverse =
    s.kind === 'STRATEGY'
      ? {
          target_kind: 'SYMBOL',
          symbols: [{ exchange: s.exchange, symbol: s.symbol }],
        }
      : {
          target_kind: 'GROUP',
          group_id: typeof s.group_id === 'number' ? s.group_id : null,
        }

  const daily_via_intraday =
    s.timeframe === '1d'
      ? {
          enabled: s.daily_via_intraday_enabled,
          base_timeframe: s.base_timeframe,
          proxy_close_hhmm: s.proxy_close_hhmm,
        }
      : null

  const baseConfig: Record<string, unknown> = {
    timeframe: s.timeframe,
    daily_via_intraday: daily_via_intraday,
    entry_dsl: s.entry_dsl,
    exit_dsl: s.exit_dsl,
    product: s.product,
    direction: s.direction,
    acknowledge_short_risk: s.acknowledge_short_risk,
    enter_immediately_on_start: s.enter_immediately_on_start,
    acknowledge_enter_immediately_risk: s.acknowledge_enter_immediately_risk,
    broker_name: s.broker_name,
    execution_target: s.execution_target,
    initial_cash: s.initial_cash,
    stop_loss_pct: s.stop_loss_pct,
    take_profit_pct: s.take_profit_pct,
    trailing_stop_pct: s.trailing_stop_pct,
    max_equity_dd_global_pct: s.max_equity_dd_global_pct,
    max_equity_dd_trade_pct: s.max_equity_dd_trade_pct,
  }

  const config: Record<string, unknown> =
    s.kind === 'STRATEGY'
      ? {
          ...baseConfig,
          position_size_pct: s.position_size_pct,
        }
      : {
          ...baseConfig,
          max_open_positions: s.max_open_positions,
          allocation_mode: s.allocation_mode,
          ranking_window: s.ranking_window,
          sizing_mode: s.sizing_mode,
          position_size_pct: s.position_size_pct,
          fixed_cash_per_trade: s.fixed_cash_per_trade,
          min_holding_bars: s.min_holding_bars,
          cooldown_bars: s.cooldown_bars,
        }

  return {
    name: s.name,
    description: s.description || null,
    kind: s.kind,
    enabled: false,
    universe,
    config,
  }
}

function prefillToEditor(prefill: DeploymentPrefill): EditorState {
  const base = defaultEditorState()
  const cfg = prefill.config ?? {}
  const uni = prefill.universe ?? { target_kind: 'SYMBOL', symbols: [] }
  const sym0 = Array.isArray(uni.symbols) ? uni.symbols[0] : undefined
  return {
    ...base,
    kind: prefill.kind,
    target_kind: uni.target_kind,
    exchange: String(sym0?.exchange ?? base.exchange),
    symbol: String(sym0?.symbol ?? base.symbol),
    group_id: typeof uni.group_id === 'number' ? uni.group_id : '',
    timeframe: String((cfg.timeframe as string) ?? base.timeframe),
    broker_name: ((cfg.broker_name as 'zerodha' | 'angelone') ??
      base.broker_name) as EditorState['broker_name'],
    execution_target: ((cfg.execution_target as 'PAPER' | 'LIVE') ??
      base.execution_target) as 'PAPER' | 'LIVE',
    product: ((cfg.product as 'CNC' | 'MIS') ?? base.product) as 'CNC' | 'MIS',
    direction: ((cfg.direction as 'LONG' | 'SHORT') ??
      base.direction) as 'LONG' | 'SHORT',
    acknowledge_short_risk: Boolean(
      (cfg.acknowledge_short_risk as boolean | undefined) ?? base.acknowledge_short_risk,
    ),
    enter_immediately_on_start: Boolean(
      (cfg.enter_immediately_on_start as boolean | undefined) ??
        base.enter_immediately_on_start,
    ),
    acknowledge_enter_immediately_risk: Boolean(
      (cfg.acknowledge_enter_immediately_risk as boolean | undefined) ??
        base.acknowledge_enter_immediately_risk,
    ),
    entry_dsl: String((cfg.entry_dsl as string) ?? base.entry_dsl),
    exit_dsl: String((cfg.exit_dsl as string) ?? base.exit_dsl),
    initial_cash: Number((cfg.initial_cash as number) ?? base.initial_cash),
    position_size_pct: Number(
      (cfg.position_size_pct as number) ?? base.position_size_pct,
    ),
    stop_loss_pct: Number((cfg.stop_loss_pct as number) ?? base.stop_loss_pct),
    take_profit_pct: Number(
      (cfg.take_profit_pct as number) ?? base.take_profit_pct,
    ),
    trailing_stop_pct: Number(
      (cfg.trailing_stop_pct as number) ?? base.trailing_stop_pct,
    ),
    max_open_positions: Number(
      (cfg.max_open_positions as number) ?? base.max_open_positions,
    ),
    allocation_mode: ((cfg.allocation_mode as 'EQUAL' | 'RANKING') ??
      base.allocation_mode) as 'EQUAL' | 'RANKING',
    ranking_window: Number((cfg.ranking_window as number) ?? base.ranking_window),
    sizing_mode: ((cfg.sizing_mode as 'PCT_EQUITY' | 'FIXED_CASH' | 'CASH_PER_SLOT') ??
      base.sizing_mode) as 'PCT_EQUITY' | 'FIXED_CASH' | 'CASH_PER_SLOT',
    fixed_cash_per_trade: Number(
      (cfg.fixed_cash_per_trade as number) ?? base.fixed_cash_per_trade,
    ),
    min_holding_bars: Number(
      (cfg.min_holding_bars as number) ?? base.min_holding_bars,
    ),
    cooldown_bars: Number((cfg.cooldown_bars as number) ?? base.cooldown_bars),
    max_equity_dd_global_pct: Number(
      (cfg.max_equity_dd_global_pct as number) ?? base.max_equity_dd_global_pct,
    ),
    max_equity_dd_trade_pct: Number(
      (cfg.max_equity_dd_trade_pct as number) ?? base.max_equity_dd_trade_pct,
    ),
    daily_via_intraday_enabled:
      (cfg.daily_via_intraday as { enabled?: boolean } | null)?.enabled ??
      base.daily_via_intraday_enabled,
    base_timeframe:
      ((cfg.daily_via_intraday as { base_timeframe?: string } | null)
        ?.base_timeframe as EditorState['base_timeframe']) ?? base.base_timeframe,
    proxy_close_hhmm:
      String(
        (cfg.daily_via_intraday as { proxy_close_hhmm?: string } | null)
          ?.proxy_close_hhmm,
      ) || base.proxy_close_hhmm,
  }
}

export function DeploymentsPage() {
  const [deployments, setDeployments] = useState<StrategyDeployment[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editor, setEditor] = useState<EditorState>(() => defaultEditorState())
  const [groups, setGroups] = useState<Array<{ id: number; name: string }>>([])
  const [symbolOptions, setSymbolOptions] = useState<MarketSymbol[]>([])
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false)
  const [symbolOptionsError, setSymbolOptionsError] = useState<string | null>(null)
  const [kindFilter, setKindFilter] = useState<DeploymentKind | 'ALL'>('ALL')
  const [execFilter, setExecFilter] = useState<'ALL' | 'PAPER' | 'LIVE'>('ALL')
  const [brokerFilter, setBrokerFilter] = useState<
    'ALL' | EditorState['broker_name']
  >('ALL')
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false)
  const [pauseTarget, setPauseTarget] = useState<StrategyDeployment | null>(null)
  const [pauseReason, setPauseReason] = useState('')
  const [startConfirmOpen, setStartConfirmOpen] = useState(false)
  const [startConfirmTarget, setStartConfirmTarget] = useState<StrategyDeployment | null>(
    null,
  )
  const [startConfirmMode, setStartConfirmMode] = useState<'START' | 'RESUME'>('START')
  const [startConfirmAckShort, setStartConfirmAckShort] = useState(false)
  const [startConfirmAckEnter, setStartConfirmAckEnter] = useState(false)
  const [exposureWarnOpen, setExposureWarnOpen] = useState(false)
  const [exposureWarnTarget, setExposureWarnTarget] = useState<StrategyDeployment | null>(
    null,
  )

  const navigate = useNavigate()
  const location = useLocation()

  const state = (location.state ?? {}) as LocationState
  useEffect(() => {
    if (!state.deploymentPrefill) return
    setEditor(prefillToEditor(state.deploymentPrefill))
    setEditorOpen(true)
    navigate('/deployments', { replace: true, state: {} })
  }, [navigate, state.deploymentPrefill])

  const refresh = async () => {
    setError(null)
    setLoading(true)
    try {
      const data = await listDeployments()
      setDeployments(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load deployments')
    } finally {
      setLoading(false)
    }
  }

  const runStartOrResume = async (dep: StrategyDeployment, mode: 'START' | 'RESUME') => {
    const dir = String((dep.config ?? {}).direction ?? '').toUpperCase()
    const enterOnStart = Boolean((dep.config ?? {}).enter_immediately_on_start)
    const needsShort = dir === 'SHORT'
    const needsEnter = enterOnStart

    if (needsShort || needsEnter) {
      setStartConfirmTarget(dep)
      setStartConfirmMode(mode)
      setStartConfirmAckShort(false)
      setStartConfirmAckEnter(false)
      setStartConfirmOpen(true)
      return
    }

    try {
      const res =
        mode === 'RESUME' ? await resumeDeployment(dep.id) : await startDeployment(dep.id)
      await refresh()
      const symbols = (res.state?.exposure?.symbols ?? []) as any[]
      const hasBrokerExposure = symbols.some((s) => Number(s?.broker_net_qty ?? 0) !== 0)
      if (hasBrokerExposure) {
        setExposureWarnTarget(res)
        setExposureWarnOpen(true)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed')
    }
  }

  useEffect(() => {
    void refresh()
    void (async () => {
      try {
        const gs = await listGroups()
        setGroups(gs.map((g) => ({ id: g.id, name: g.name })))
      } catch {
        setGroups([])
      }
    })()
  }, [])

  useEffect(() => {
    if (!editorOpen) return
    if (editor.kind !== 'STRATEGY') return

    const q = editor.symbol.trim()
    if (q.length < 1) {
      setSymbolOptions([])
      setSymbolOptionsError(null)
      return
    }

    let active = true
    setSymbolOptionsLoading(true)
    setSymbolOptionsError(null)
    const id = window.setTimeout(() => {
      void (async () => {
        try {
          const res = await searchMarketSymbols({
            q,
            exchange: editor.exchange.trim().toUpperCase() || undefined,
            limit: 30,
          })
          if (!active) return
          setSymbolOptions(res)
        } catch (err) {
          if (!active) return
          setSymbolOptions([])
          setSymbolOptionsError(
            err instanceof Error ? err.message : 'Failed to search symbols',
          )
        } finally {
          if (!active) return
          setSymbolOptionsLoading(false)
        }
      })()
    }, 200)
    return () => {
      active = false
      window.clearTimeout(id)
    }
  }, [editor.exchange, editor.kind, editor.symbol, editorOpen])

  const filteredDeployments = useMemo(() => {
    const getCfgStr = (dep: StrategyDeployment, key: string): string => {
      const cfg = (dep.config ?? {}) as Record<string, unknown>
      const v = cfg[key]
      return typeof v === 'string' ? v : ''
    }
    return deployments.filter((d) => {
      if (kindFilter !== 'ALL' && d.kind !== kindFilter) return false
      const exec = getCfgStr(d, 'execution_target').toUpperCase() || 'PAPER'
      if (execFilter !== 'ALL' && exec !== execFilter) return false
      const broker =
        getCfgStr(d, 'broker_name').toLowerCase() || 'zerodha'
      if (brokerFilter !== 'ALL' && broker !== brokerFilter) return false
      return true
    })
  }, [brokerFilter, deployments, execFilter, kindFilter])

  const columns = useMemo<GridColDef[]>(
    () => [
      { field: 'id', headerName: 'ID', width: 80 },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 180 },
      { field: 'kind', headerName: 'Kind', width: 170 },
      {
        field: 'broker',
        headerName: 'Broker',
        width: 110,
        valueGetter: (_value, row) =>
          String((row as StrategyDeployment).config?.broker_name ?? 'zerodha'),
      },
      {
        field: 'execution',
        headerName: 'Exec',
        width: 100,
        valueGetter: (_value, row) =>
          String((row as StrategyDeployment).config?.execution_target ?? 'PAPER'),
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 130,
        valueGetter: (_value, row) =>
          (row as StrategyDeployment).state?.status ?? '—',
        renderCell: (p) => {
          const s = String(p.value ?? '')
          return (
            <Chip
              size="small"
              label={s || '—'}
              color={statusColor(s)}
              variant={statusColor(s) === 'default' ? 'outlined' : 'filled'}
            />
          )
        },
      },
      {
        field: 'last_evaluated_at',
        headerName: 'Last Eval',
        width: 190,
        valueGetter: (_value, row) =>
          (row as StrategyDeployment).state?.last_evaluated_at ?? null,
        renderCell: (p) => <>{fmtTs(p.value as string | null)}</>,
      },
      {
        field: 'open_positions',
        headerName: 'Open',
        width: 90,
        valueGetter: (_value, row) =>
          (row as StrategyDeployment).state_summary?.open_positions ?? 0,
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 220,
        sortable: false,
        filterable: false,
        renderCell: (p) => {
          const dep = p.row as StrategyDeployment
          const running = String(dep.state?.status ?? '').toUpperCase() === 'RUNNING'
          const paused = String(dep.state?.status ?? '').toUpperCase() === 'PAUSED'
          const mismatch =
            paused &&
            String(dep.state?.runtime_state ?? '').toUpperCase() ===
              'PAUSED_DIRECTION_MISMATCH'
          return (
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Tooltip title="Open details">
                <IconButton
                  size="small"
                  onClick={() => navigate(`/deployments/${dep.id}`)}
                >
                  <OpenInNewIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              {running ? (
                <Tooltip title="Pause (evaluations stop; protections remain active)">
                  <IconButton
                    size="small"
                    onClick={() => {
                      setPauseTarget(dep)
                      setPauseReason(dep.state?.pause_reason ?? '')
                      setPauseDialogOpen(true)
                    }}
                  >
                    <PauseIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              ) : null}
              {paused ? (
                <Tooltip
                  title={
                    mismatch
                      ? 'Resolve direction mismatch in details first.'
                      : 'Resume'
                  }
                >
                  <IconButton
                    size="small"
                    disabled={mismatch}
                    onClick={() => {
                      void runStartOrResume(dep, 'RESUME')
                    }}
                  >
                    <PlayArrowIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              ) : null}
              {!running && !paused ? (
                <Tooltip title="Start">
                  <IconButton
                    size="small"
                    onClick={() => {
                      void runStartOrResume(dep, 'START')
                    }}
                  >
                    <PlayArrowIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              ) : null}
              <Tooltip title="Stop">
                <IconButton
                  size="small"
                  disabled={!running && !paused}
                  onClick={() => {
                    void (async () => {
                      try {
                        await stopDeployment(dep.id)
                        await refresh()
                      } catch (err) {
                        setError(err instanceof Error ? err.message : 'Failed')
                      }
                    })()
                  }}
                >
                  <StopIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Edit">
                <IconButton
                  size="small"
                  onClick={() => {
                    const next = prefillToEditor({
                      kind: dep.kind,
                      universe: dep.universe,
                      config: dep.config,
                    })
                    setEditor({
                      ...next,
                      id: dep.id,
                      name: dep.name,
                      description: dep.description ?? '',
                    })
                    setEditorOpen(true)
                  }}
                >
                  <EditIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Delete">
                <IconButton
                  size="small"
                  onClick={() => {
                    void (async () => {
                      try {
                        await deleteDeployment(dep.id)
                        await refresh()
                      } catch (err) {
                        setError(err instanceof Error ? err.message : 'Failed')
                      }
                    })()
                  }}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          )
        },
      },
    ],
    [navigate],
  )

  const save = async () => {
    setError(null)
    try {
      const payload = editorToPayload(editor)
      if (editor.kind === 'PORTFOLIO_STRATEGY' && !payload.universe.group_id) {
        throw new Error('Group is required for portfolio deployments.')
      }
      if (editor.id) {
        await updateDeployment(editor.id, {
          name: payload.name,
          description: payload.description ?? null,
          universe: payload.universe,
          config: payload.config,
        })
      } else {
        await createDeployment(payload)
      }
      setEditorOpen(false)
      setEditor(defaultEditorState())
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    }
  }

  return (
    <Box sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="h6">Deployments</Typography>
            <Tooltip title="Help">
            <IconButton size="small" onClick={() => setHelpOpen(true)}>
              <HelpOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Box sx={{ flexGrow: 1 }} />
          <Button
            startIcon={<AddIcon />}
            variant="contained"
            onClick={() => {
              setEditor(defaultEditorState())
              setEditorOpen(true)
            }}
          >
            New
          </Button>
          <Button variant="outlined" onClick={() => void refresh()} disabled={loading}>
            Refresh
          </Button>
          </Stack>

          {error ? <Alert severity="error">{error}</Alert> : null}

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Kind</InputLabel>
              <Select
                label="Kind"
                value={kindFilter}
                onChange={(e) => setKindFilter(e.target.value as any)}
              >
                <MenuItem value="ALL">All</MenuItem>
                <MenuItem value="STRATEGY">Single symbol</MenuItem>
                <MenuItem value="PORTFOLIO_STRATEGY">Portfolio (Group)</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel>Execution</InputLabel>
              <Select
                label="Execution"
                value={execFilter}
                onChange={(e) => setExecFilter(e.target.value as any)}
              >
                <MenuItem value="ALL">All</MenuItem>
                <MenuItem value="PAPER">Paper</MenuItem>
                <MenuItem value="LIVE">Live</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel>Broker</InputLabel>
              <Select
                label="Broker"
                value={brokerFilter}
                onChange={(e) => setBrokerFilter(e.target.value as any)}
              >
                <MenuItem value="ALL">All</MenuItem>
                <MenuItem value="zerodha">Zerodha</MenuItem>
                <MenuItem value="angelone">Angel One</MenuItem>
              </Select>
            </FormControl>
            <Box sx={{ flexGrow: 1 }} />
            <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>
              Showing {filteredDeployments.length} / {deployments.length}
            </Typography>
          </Stack>

          <Box sx={{ height: 'calc(100vh - 200px)', minHeight: 360 }}>
            <DataGrid
              rows={filteredDeployments}
              columns={columns}
              getRowId={(r) => (r as StrategyDeployment).id}
              loading={loading}
              density="compact"
            disableRowSelectionOnClick
          />
        </Box>
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

      <Dialog open={editorOpen} onClose={() => setEditorOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{editor.id ? 'Edit deployment' : 'New deployment'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              value={editor.name}
              onChange={(e) => setEditor((p) => ({ ...p, name: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Description"
              value={editor.description}
              onChange={(e) => setEditor((p) => ({ ...p, description: e.target.value }))}
              fullWidth
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <FormControl fullWidth>
                <InputLabel>Kind</InputLabel>
                <Select
                  label="Kind"
                  value={editor.kind}
                  onChange={(e) => {
                    const k = e.target.value as DeploymentKind
                    setEditor((p) => ({
                      ...p,
                      kind: k,
                      target_kind: k === 'STRATEGY' ? 'SYMBOL' : 'GROUP',
                    }))
                  }}
                >
                  <MenuItem value="STRATEGY">Single symbol</MenuItem>
                  <MenuItem value="PORTFOLIO_STRATEGY">Portfolio (Group)</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel>Timeframe</InputLabel>
                <Select
                  label="Timeframe"
                  value={editor.timeframe}
                  onChange={(e) => setEditor((p) => ({ ...p, timeframe: String(e.target.value) }))}
                >
                  {['1m', '5m', '15m', '30m', '1h', '1d'].map((tf) => (
                    <MenuItem key={tf} value={tf}>
                      {tf}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>

            {editor.kind === 'STRATEGY' ? (
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Exchange"
                  value={editor.exchange}
                  onChange={(e) => setEditor((p) => ({ ...p, exchange: e.target.value }))}
                  sx={{ width: { xs: '100%', sm: 140 } }}
                />
                <Autocomplete<MarketSymbol, false, false, true>
                  freeSolo
                  clearOnBlur={false}
                  options={symbolOptions}
                  loading={symbolOptionsLoading}
                  sx={{ flex: 1, minWidth: 0 }}
                  value={
                    symbolOptions.find(
                      (o) =>
                        o.symbol.toUpperCase() === editor.symbol.trim().toUpperCase()
                        && o.exchange.toUpperCase() === editor.exchange.trim().toUpperCase(),
                    ) ?? null
                  }
                  onChange={(_e, value) => {
                    if (typeof value === 'string') {
                      setEditor((p) => ({ ...p, symbol: value.toUpperCase() }))
                      return
                    }
                    if (value?.exchange) {
                      setEditor((p) => ({
                        ...p,
                        exchange: value.exchange.toUpperCase(),
                        symbol: value.symbol.toUpperCase(),
                      }))
                      return
                    }
                    if (value?.symbol) {
                      setEditor((p) => ({ ...p, symbol: value.symbol.toUpperCase() }))
                    }
                  }}
                  inputValue={editor.symbol}
                  onInputChange={(_e, value) =>
                    setEditor((p) => ({ ...p, symbol: value.toUpperCase() }))
                  }
                  getOptionLabel={(o) => (typeof o === 'string' ? o : o.symbol)}
                  isOptionEqualToValue={(a, b) =>
                    typeof b === 'string'
                      ? a.symbol === b
                      : a.symbol === b.symbol && a.exchange === b.exchange
                  }
                  renderOption={(props, option) => (
                    <li {...props} key={`${option.exchange}:${option.symbol}`}>
                      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                        <Typography variant="body2">
                          {option.symbol}{' '}
                          <Typography
                            component="span"
                            variant="caption"
                            color="text.secondary"
                          >
                            ({option.exchange})
                          </Typography>
                        </Typography>
                        {option.name ? (
                          <Typography variant="caption" color="text.secondary">
                            {option.name}
                          </Typography>
                        ) : null}
                      </Box>
                    </li>
                  )}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Symbol"
                      fullWidth
                      helperText={symbolOptionsError ?? undefined}
                      error={!!symbolOptionsError}
                    />
                  )}
                />
              </Stack>
            ) : (
              <FormControl fullWidth>
                <InputLabel>Group</InputLabel>
                <Select
                  label="Group"
                  value={editor.group_id}
                  onChange={(e) => {
                    const v = e.target.value
                    setEditor((p) => ({ ...p, group_id: typeof v === 'number' ? v : Number(v) }))
                  }}
                >
                  {groups.map((g) => (
                    <MenuItem key={g.id} value={g.id}>
                      {g.name} (#{g.id})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            {editor.timeframe === '1d' ? (
              <>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={editor.daily_via_intraday_enabled}
                      onChange={(e) =>
                        setEditor((p) => ({
                          ...p,
                          daily_via_intraday_enabled: e.target.checked,
                        }))
                      }
                    />
                  }
                  label="Daily logic via intraday engine (recommended)"
                />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <FormControl fullWidth>
                    <InputLabel>Base TF</InputLabel>
                    <Select
                      label="Base TF"
                      value={editor.base_timeframe}
                      onChange={(e) =>
                        setEditor((p) => ({
                          ...p,
                          base_timeframe: e.target.value as EditorState['base_timeframe'],
                        }))
                      }
                      disabled={!editor.daily_via_intraday_enabled}
                    >
                      {['1m', '5m', '15m', '30m', '1h'].map((tf) => (
                        <MenuItem key={tf} value={tf}>
                          {tf}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <TextField
                    label="Proxy close (HH:MM)"
                    value={editor.proxy_close_hhmm}
                    onChange={(e) =>
                      setEditor((p) => ({ ...p, proxy_close_hhmm: e.target.value }))
                    }
                    disabled={!editor.daily_via_intraday_enabled}
                    fullWidth
                  />
                </Stack>
              </>
            ) : null}

            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="subtitle2">DSL</Typography>
              <Box sx={{ flexGrow: 1 }} />
              <Tooltip title="DSL help">
                <IconButton size="small" onClick={() => setHelpOpen(true)}>
                  <HelpOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
            <TextField
              label="Entry DSL"
              value={editor.entry_dsl}
              onChange={(e) => setEditor((p) => ({ ...p, entry_dsl: e.target.value }))}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField
              label="Exit DSL"
              value={editor.exit_dsl}
              onChange={(e) => setEditor((p) => ({ ...p, exit_dsl: e.target.value }))}
              fullWidth
              multiline
              minRows={2}
            />

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <FormControl fullWidth>
                <InputLabel>Broker</InputLabel>
                <Select
                  label="Broker"
                  value={editor.broker_name}
                  onChange={(e) =>
                    setEditor((p) => ({
                      ...p,
                      broker_name: e.target.value as EditorState['broker_name'],
                    }))
                  }
                >
                  <MenuItem value="zerodha">Zerodha</MenuItem>
                  <MenuItem value="angelone">Angel One</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel>Execution</InputLabel>
                <Select
                  label="Execution"
                  value={editor.execution_target}
                  onChange={(e) =>
                    setEditor((p) => ({
                      ...p,
                      execution_target: e.target.value as EditorState['execution_target'],
                    }))
                  }
                >
                  <MenuItem value="PAPER">Paper</MenuItem>
                  <MenuItem value="LIVE">Live</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel>Product</InputLabel>
                <Select
                  label="Product"
                  value={editor.product}
                  onChange={(e) => {
                    const nextProduct = e.target.value as EditorState['product']
                    setEditor((p) => ({
                      ...p,
                      product: nextProduct,
                      direction:
                        nextProduct === 'CNC' && p.direction === 'SHORT'
                          ? 'LONG'
                          : p.direction,
                      acknowledge_short_risk:
                        nextProduct === 'CNC' ? false : p.acknowledge_short_risk,
                    }))
                  }}
                >
                  <MenuItem value="CNC">CNC</MenuItem>
                  <MenuItem value="MIS">MIS</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel>Direction</InputLabel>
                <Select
                  label="Direction"
                  value={editor.direction}
                  onChange={(e) => {
                    const nextDir = e.target.value as EditorState['direction']
                    setEditor((p) => ({
                      ...p,
                      direction: nextDir,
                      product: nextDir === 'SHORT' ? 'MIS' : p.product,
                      acknowledge_short_risk: nextDir === 'SHORT' ? p.acknowledge_short_risk : false,
                    }))
                  }}
                >
                  <MenuItem value="LONG">LONG</MenuItem>
                  <MenuItem value="SHORT">SHORT</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            {editor.direction === 'SHORT' ? (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={editor.acknowledge_short_risk}
                    onChange={(e) =>
                      setEditor((p) => ({
                        ...p,
                        acknowledge_short_risk: e.target.checked,
                        product: 'MIS',
                      }))
                    }
                  />
                }
                label={
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <span>Acknowledge short-selling risk (required)</span>
                    <Tooltip title="Short deployments can amplify losses; only MIS is allowed.">
                      <HelpOutlineIcon fontSize="small" />
                    </Tooltip>
                  </Stack>
                }
              />
            ) : null}

            <FormControlLabel
              control={
                <Checkbox
                  checked={editor.enter_immediately_on_start}
                  onChange={(e) =>
                    setEditor((p) => ({
                      ...p,
                      enter_immediately_on_start: e.target.checked,
                      acknowledge_enter_immediately_risk: e.target.checked
                        ? p.acknowledge_enter_immediately_risk
                        : false,
                    }))
                  }
                />
              }
              label={
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <span>Enter immediately on start (advanced)</span>
                  <Tooltip title="Enqueues an immediate evaluation on start; can trigger trades quickly.">
                    <HelpOutlineIcon fontSize="small" />
                  </Tooltip>
                </Stack>
              }
            />
            {editor.enter_immediately_on_start ? (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={editor.acknowledge_enter_immediately_risk}
                    onChange={(e) =>
                      setEditor((p) => ({
                        ...p,
                        acknowledge_enter_immediately_risk: e.target.checked,
                      }))
                    }
                  />
                }
                label="I understand enter-on-start can cause immediate trades (required)"
              />
            ) : null}

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Initial cash (paper)"
                type="number"
                value={editor.initial_cash}
                onChange={(e) =>
                  setEditor((p) => ({ ...p, initial_cash: Number(e.target.value) }))
                }
                fullWidth
              />
              <TextField
                label="Stop loss %"
                type="number"
                value={editor.stop_loss_pct}
                onChange={(e) =>
                  setEditor((p) => ({ ...p, stop_loss_pct: Number(e.target.value) }))
                }
                fullWidth
              />
              <TextField
                label="Trailing stop %"
                type="number"
                value={editor.trailing_stop_pct}
                onChange={(e) =>
                  setEditor((p) => ({
                    ...p,
                    trailing_stop_pct: Number(e.target.value),
                  }))
                }
                fullWidth
              />
            </Stack>

            {editor.kind === 'PORTFOLIO_STRATEGY' ? (
              <>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField
                    label="Max open positions"
                    type="number"
                    value={editor.max_open_positions}
                    onChange={(e) =>
                      setEditor((p) => ({
                        ...p,
                        max_open_positions: Number(e.target.value),
                      }))
                    }
                    fullWidth
                  />
                  <FormControl fullWidth>
                    <InputLabel>Allocation</InputLabel>
                    <Select
                      label="Allocation"
                      value={editor.allocation_mode}
                      onChange={(e) =>
                        setEditor((p) => ({
                          ...p,
                          allocation_mode: e.target.value as EditorState['allocation_mode'],
                        }))
                      }
                    >
                      <MenuItem value="EQUAL">Equal</MenuItem>
                      <MenuItem value="RANKING">Ranking</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    label="Ranking window"
                    type="number"
                    value={editor.ranking_window}
                    onChange={(e) =>
                      setEditor((p) => ({
                        ...p,
                        ranking_window: Number(e.target.value),
                      }))
                    }
                    fullWidth
                  />
                </Stack>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <FormControl fullWidth>
                    <InputLabel>Sizing</InputLabel>
                    <Select
                      label="Sizing"
                      value={editor.sizing_mode}
                      onChange={(e) =>
                        setEditor((p) => ({
                          ...p,
                          sizing_mode: e.target.value as EditorState['sizing_mode'],
                        }))
                      }
                    >
                      <MenuItem value="PCT_EQUITY">Pct equity</MenuItem>
                      <MenuItem value="FIXED_CASH">Fixed cash</MenuItem>
                      <MenuItem value="CASH_PER_SLOT">Cash per slot</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    label="Position size %"
                    type="number"
                    value={editor.position_size_pct}
                    onChange={(e) =>
                      setEditor((p) => ({
                        ...p,
                        position_size_pct: Number(e.target.value),
                      }))
                    }
                    fullWidth
                  />
                  <TextField
                    label="Fixed cash per trade"
                    type="number"
                    value={editor.fixed_cash_per_trade}
                    onChange={(e) =>
                      setEditor((p) => ({
                        ...p,
                        fixed_cash_per_trade: Number(e.target.value),
                      }))
                    }
                    fullWidth
                  />
                </Stack>
              </>
            ) : (
              <TextField
                label="Position size %"
                type="number"
                value={editor.position_size_pct}
                onChange={(e) =>
                  setEditor((p) => ({
                    ...p,
                    position_size_pct: Number(e.target.value),
                  }))
                }
                fullWidth
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditorOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => void save()}
            disabled={
              (editor.direction === 'SHORT' && !editor.acknowledge_short_risk) ||
              (editor.enter_immediately_on_start &&
                !editor.acknowledge_enter_immediately_risk)
            }
          >
            Save
          </Button>
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
              if (!pauseTarget) return
              void (async () => {
                try {
                  await pauseDeployment(pauseTarget.id, pauseReason)
                  setPauseDialogOpen(false)
                  setPauseTarget(null)
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
            {String((startConfirmTarget?.config ?? {}).direction ?? '').toUpperCase() ===
            'SHORT' ? (
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
            {Boolean((startConfirmTarget?.config ?? {}).enter_immediately_on_start) ? (
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
              (String((startConfirmTarget?.config ?? {}).direction ?? '').toUpperCase() ===
                'SHORT' &&
                !startConfirmAckShort) ||
              (Boolean((startConfirmTarget?.config ?? {}).enter_immediately_on_start) &&
                !startConfirmAckEnter)
            }
            onClick={() => {
              if (!startConfirmTarget) return
              void (async () => {
                try {
                  const res =
                    startConfirmMode === 'RESUME'
                      ? await resumeDeployment(startConfirmTarget.id)
                      : await startDeployment(startConfirmTarget.id)
                  setStartConfirmOpen(false)
                  setStartConfirmTarget(null)
                  await refresh()
                  const symbols = (res.state?.exposure?.symbols ?? []) as any[]
                  const hasBrokerExposure = symbols.some(
                    (s) => Number(s?.broker_net_qty ?? 0) !== 0,
                  )
                  if (hasBrokerExposure) {
                    setExposureWarnTarget(res)
                    setExposureWarnOpen(true)
                  }
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

      <Dialog
        open={exposureWarnOpen}
        onClose={() => setExposureWarnOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Existing exposure detected</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Existing broker positions were detected. Running this deployment may place
              duplicate orders or increase exposure.
            </Typography>
            <Typography variant="body2">
              Deployment: {exposureWarnTarget?.name ?? '—'}
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExposureWarnOpen(false)}>Keep running</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => {
              if (!exposureWarnTarget) return
              void (async () => {
                try {
                  await pauseDeployment(exposureWarnTarget.id, 'Paused after exposure warning.')
                  setExposureWarnOpen(false)
                  setExposureWarnTarget(null)
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
    </Box>
  )
}
