import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Autocomplete from '@mui/material/Autocomplete'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Switch from '@mui/material/Switch'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { DslHelpDialog } from '../components/DslHelpDialog'
import { DslEditor } from '../components/DslEditor'
import { fetchBrokers, type BrokerInfo } from '../services/brokers'
import { listGroups, type Group } from '../services/groups'
import { searchMarketSymbols, type MarketSymbol } from '../services/marketData'
import {
  createAlertDefinition,
  createCustomIndicator,
  deleteAlertDefinition,
  deleteCustomIndicator,
  listAlertDefinitions,
  listAlertEvents,
  listCustomIndicators,
  updateAlertDefinition,
  updateCustomIndicator,
  type AlertDefinition,
  type AlertDefinitionCreate,
  type AlertDefinitionUpdate,
  type AlertEvent,
  type AlertVariableDef,
  type CustomIndicator,
  type CustomIndicatorCreate,
	type CustomIndicatorUpdate,
} from '../services/alertsV3'
import { ALERT_V3_METRICS, ALERT_V3_SOURCES, ALERT_V3_TIMEFRAMES } from '../services/alertsV3Constants'
import { useCustomIndicators } from '../hooks/useCustomIndicators'
import {
  getSignalStrategyVersion,
  listSignalStrategies,
  listSignalStrategyVersions,
  type SignalStrategy,
  type SignalStrategyVersion,
} from '../services/signalStrategies'
import { SignalStrategiesTab } from './SignalStrategiesTab'

const formatDateTimeIst = (value: unknown): string => {
  if (!value) return '—'
  const raw = String(value)
  const normalized =
    raw.includes(' ') && !raw.includes('T') ? raw.replace(' ', 'T') : raw
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(normalized)

  let dt = new Date(normalized)
  if (!hasTz) {
    const m = normalized.match(
      /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/,
    )
    if (m) {
      const [, y, mo, d, h, mi, s] = m
      const istOffsetMs = 5.5 * 60 * 60 * 1000
      const utcMs = Date.UTC(+y, +mo - 1, +d, +h, +mi, +s) - istOffsetMs
      dt = new Date(utcMs)
    }
  }

  if (Number.isNaN(dt.getTime())) return '—'
  return dt.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })
}

export function AlertsPage() {
  const [tab, setTab] = useState(0)
  const [openAlertId, setOpenAlertId] = useState<number | null>(null)
  const [createDefaults, setCreateDefaults] = useState<{
    targetKind: 'SYMBOL'
    targetRef: string
    exchange: string
  } | null>(null)

  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const tabParam = (params.get('tab') || '').toLowerCase()
    if (tabParam === 'indicators') setTab(1)
    if (tabParam === 'events') setTab(2)
    if (tabParam === 'strategies') setTab(3)
  }, [location.search])

  const handleOpenAlert = (alertId: number) => {
    setOpenAlertId(alertId)
    setTab(0)
  }

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('create_v3') !== '1') return
    const kind = (params.get('target_kind') || '').toUpperCase()
    if (kind !== 'SYMBOL') return
    const targetRef = (params.get('target_ref') || '').trim()
    if (!targetRef) return
    const exchange = (params.get('exchange') || 'NSE').trim().toUpperCase() || 'NSE'
    setTab(0)
    setCreateDefaults({ targetKind: 'SYMBOL', targetRef: targetRef.toUpperCase(), exchange })
    navigate('/alerts', { replace: true })
  }, [location.search, navigate])

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Alerts
      </Typography>
      <Tabs
        value={tab}
        onChange={(_e, v) => setTab(v)}
        sx={{ mb: 2 }}
      >
        <Tab label="Alerts" />
        <Tab label="Indicators" />
        <Tab label="Events" />
        <Tab label="Strategies" />
      </Tabs>
      {tab === 0 && (
        <AlertsV3Tab
          openAlertId={openAlertId}
          onAlertOpened={() => setOpenAlertId(null)}
          createDefaults={createDefaults}
          onCreateHandled={() => setCreateDefaults(null)}
        />
      )}
      {tab === 1 && <IndicatorsV3Tab />}
      {tab === 2 && <EventsV3Tab onOpenAlert={handleOpenAlert} />}
      {tab === 3 && <SignalStrategiesTab />}
    </Box>
	  )
	}

function AlertsV3Tab({
	  openAlertId,
	  onAlertOpened,
	  createDefaults,
  onCreateHandled,
}: {
  openAlertId: number | null
  onAlertOpened: () => void
  createDefaults: { targetKind: 'SYMBOL'; targetRef: string; exchange: string } | null
  onCreateHandled: () => void
}) {
  const [rows, setRows] = useState<AlertDefinition[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<AlertDefinition | null>(null)
  const [activeCreateDefaults, setActiveCreateDefaults] = useState<{
    targetKind: 'SYMBOL'
    targetRef: string
    exchange: string
  } | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await listAlertDefinitions()
      setRows(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  useEffect(() => {
    void (async () => {
      try {
        const list = await fetchBrokers()
        setBrokers(list)
      } catch {
        // ignore
      }
    })()
  }, [])

  useEffect(() => {
    void (async () => {
      try {
        const res = await listGroups()
        setGroups(res)
      } catch {
        // ignore
      }
    })()
  }, [])

  useEffect(() => {
    if (openAlertId == null) return
    const open = async () => {
      try {
        setLoading(true)
        setError(null)
        const res = await listAlertDefinitions()
        setRows(res)
        const found = res.find((a) => a.id === openAlertId) ?? null
        if (!found) {
          setError(`Alert ${openAlertId} not found.`)
          return
        }
        setEditing(found)
        setEditorOpen(true)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to open alert')
      } finally {
        setLoading(false)
        onAlertOpened()
      }
    }
    void open()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openAlertId])

  useEffect(() => {
    if (!createDefaults) return
    setActiveCreateDefaults(createDefaults)
    setEditing(null)
    setEditorOpen(true)
    onCreateHandled()
  }, [createDefaults, onCreateHandled])

  const formatIstDateTime = (value: unknown): string => {
    return formatDateTimeIst(value)
  }

  const brokerLabelByName = useMemo(() => {
    const m = new Map<string, string>()
    for (const b of brokers) m.set(b.name, b.label)
    return m
  }, [brokers])

  const groupLabelById = useMemo(() => {
    const m = new Map<string, string>()
    for (const g of groups) {
      m.set(String(g.id), g.name)
    }
    return m
  }, [groups])

  const columns: GridColDef[] = [
    { field: 'name', headerName: 'Name', flex: 1, minWidth: 220 },
    {
      field: 'target',
      headerName: 'Target',
      width: 220,
      valueGetter: (_v, row) => {
        const brokerLabel =
          brokerLabelByName.get(row.broker_name) ?? row.broker_name
        if (row.target_kind === 'HOLDINGS') return `Holdings (${brokerLabel})`
        if (row.target_kind === 'GROUP') {
          const label = groupLabelById.get(String(row.target_ref)) ?? row.target_ref
          return `Group: ${label} (${brokerLabel})`
        }
        const sym = row.symbol ?? row.target_ref
        return `${sym} / ${(row.exchange ?? 'NSE').toString()} (${brokerLabel})`
      },
    },
    {
      field: 'evaluation_cadence',
      headerName: 'Cadence',
      width: 110,
    },
    {
      field: 'enabled',
      headerName: 'Status',
      width: 110,
      renderCell: (params: GridRenderCellParams<AlertDefinition, boolean>) => (
        <Chip
          size="small"
          label={params.value ? 'Enabled' : 'Paused'}
          color={params.value ? 'success' : 'default'}
        />
      ),
    },
    {
      field: 'last_triggered_at',
      headerName: 'Last trigger',
      width: 180,
      valueFormatter: (v) => formatIstDateTime(v),
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 220,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const row = params.row as AlertDefinition
        return (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                setEditing(row)
                setEditorOpen(true)
              }}
            >
              Edit
            </Button>
            <Button
              size="small"
              color="error"
              onClick={async () => {
                const ok = window.confirm(`Delete alert '${row.name}'?`)
                if (!ok) return
                try {
                  await deleteAlertDefinition(row.id)
                  await refresh()
                } catch (err) {
                  setError(
                    err instanceof Error ? err.message : 'Failed to delete alert',
                  )
                }
              }}
            >
              Delete
            </Button>
          </Box>
        )
      },
    },
  ]

  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Indicator-first alerts over universes. Alerts can emit events and optionally place broker-bound orders.
      </Typography>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
        <Button
          variant="contained"
          onClick={() => {
            setEditing(null)
            setEditorOpen(true)
          }}
        >
          Create alert
        </Button>
        <Button variant="outlined" onClick={() => void refresh()} disabled={loading}>
          Refresh
        </Button>
      </Box>
      <Paper sx={{ height: 520, width: '100%' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          density="compact"
          loading={loading}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          initialState={{
            pagination: { paginationModel: { pageSize: 25 } },
          }}
          pageSizeOptions={[25, 50, 100]}
          localeText={{
            noRowsLabel: loading ? 'Loading alerts...' : 'No v3 alerts found.',
          }}
        />
      </Paper>
      <AlertV3EditorDialog
        open={editorOpen}
        alert={editing}
        brokers={brokers}
        groups={groups}
        onClose={() => {
          setEditorOpen(false)
          setActiveCreateDefaults(null)
        }}
        onSaved={() => void refresh()}
        createDefaults={activeCreateDefaults}
      />
    </Box>
  )
}

type AlertV3EditorDialogProps = {
  open: boolean
  alert: AlertDefinition | null
  brokers: BrokerInfo[]
  groups: Group[]
  onClose: () => void
  onSaved: () => void
  createDefaults?: { targetKind: 'SYMBOL'; targetRef: string; exchange: string } | null
}

function AlertV3EditorDialog({
  open,
  alert,
  brokers,
  groups,
  onClose,
  onSaved,
  createDefaults,
}: AlertV3EditorDialogProps) {
	  type VariableKind =
	    | 'DSL'
	    | 'METRIC'
	    | 'PRICE'
	    | 'OPEN'
	    | 'HIGH'
	    | 'LOW'
	    | 'CLOSE'
	    | 'VOLUME'
	    | 'SMA'
	    | 'EMA'
	    | 'RSI'
	    | 'STDDEV'
	    | 'RET'
	    | 'ATR'
	    | 'OBV'
	    | 'VWAP'
	    | 'CUSTOM'

  type ConditionOp =
    | '>'
    | '>='
    | '<'
    | '<='
    | '=='
    | '!='
    | 'CROSSES_ABOVE'
    | 'CROSSES_BELOW'
    | 'MOVING_UP'
    | 'MOVING_DOWN'

  type ConditionRow = {
    lhs: string
    op: ConditionOp
    rhs: string
  }

  const [helpOpen, setHelpOpen] = useState(false)
  const [name, setName] = useState('')
  const [brokerName, setBrokerName] = useState<string>('zerodha')
  const [targetKind, setTargetKind] = useState<'SYMBOL' | 'HOLDINGS' | 'GROUP'>(
    'HOLDINGS',
  )
  const [targetRef, setTargetRef] = useState('')
  const [exchange, setExchange] = useState('NSE')
  const [symbolOptions, setSymbolOptions] = useState<MarketSymbol[]>([])
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false)
  const [symbolOptionsError, setSymbolOptionsError] = useState<string | null>(null)
  const [actionType, setActionType] = useState<'ALERT_ONLY' | 'BUY' | 'SELL'>(
    'ALERT_ONLY',
  )
  const [actionTab, setActionTab] = useState<0 | 1>(0)
  const [tradeExecutionMode, setTradeExecutionMode] = useState<'MANUAL' | 'AUTO'>(
    'MANUAL',
  )
  const [tradeExecutionTarget, setTradeExecutionTarget] = useState<
    'LIVE' | 'PAPER'
  >('LIVE')
  const [tradeSizeMode, setTradeSizeMode] = useState<
    'QTY' | 'AMOUNT' | 'PCT_POSITION'
  >('QTY')
  const [tradeQty, setTradeQty] = useState<string>('')
  const [tradeAmount, setTradeAmount] = useState<string>('')
  const [tradePctPosition, setTradePctPosition] = useState<string>('')
  const [tradeOrderType, setTradeOrderType] = useState<
    'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  >('MARKET')
  const [tradePrice, setTradePrice] = useState<string>('')
  const [tradeTriggerPrice, setTradeTriggerPrice] = useState<string>('')
  const [tradeProduct, setTradeProduct] = useState<'CNC' | 'MIS'>('CNC')
  const [tradeBracketEnabled, setTradeBracketEnabled] = useState(false)
  const [tradeMtpPct, setTradeMtpPct] = useState<string>('')
  const [tradeGtt, setTradeGtt] = useState(false)
  const [evaluationCadence, setEvaluationCadence] = useState<string>('')
  const [variables, setVariables] = useState<AlertVariableDef[]>([])
  const [conditionDsl, setConditionDsl] = useState('')
  const [triggerMode, setTriggerMode] = useState<
    'ONCE' | 'ONCE_PER_BAR' | 'EVERY_TIME'
  >('ONCE_PER_BAR')
  const [throttleSeconds, setThrottleSeconds] = useState<string>('')
  const [onlyMarketHours, setOnlyMarketHours] = useState(false)
  const [expiresAt, setExpiresAt] = useState<string>('')
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conditionTab, setConditionTab] = useState<0 | 1>(0)
  const [conditionJoin, setConditionJoin] = useState<'AND' | 'OR'>('AND')
	  const [conditionRows, setConditionRows] = useState<ConditionRow[]>([
	    { lhs: '', op: '>', rhs: '' },
	  ])

    // Saved strategy linkage (optional)
    const [useSavedStrategy, setUseSavedStrategy] = useState(false)
    const [strategies, setStrategies] = useState<SignalStrategy[]>([])
    const [strategiesLoading, setStrategiesLoading] = useState(false)
    const [strategiesError, setStrategiesError] = useState<string | null>(null)
    const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(null)
    const [strategyVersions, setStrategyVersions] = useState<SignalStrategyVersion[]>([])
    const [selectedStrategyVersionId, setSelectedStrategyVersionId] = useState<number | null>(null)
    const [selectedStrategyOutput, setSelectedStrategyOutput] = useState<string | null>(null)
    const [strategyParams, setStrategyParams] = useState<Record<string, unknown>>({})

  const {
    customIndicators,
    loading: customIndicatorsLoading,
    error: customIndicatorsError,
    refresh: refreshCustomIndicators,
  } = useCustomIndicators({
    enabled: open,
  })

	  useEffect(() => {
	    if (!open) return
    if (targetKind !== 'SYMBOL') {
      setSymbolOptions([])
      setSymbolOptionsLoading(false)
      setSymbolOptionsError(null)
      return
    }
    const q = targetRef.trim()
    if (q.length < 1) {
      setSymbolOptions([])
      setSymbolOptionsError(null)
      return
    }
    const exchangeFilter = /^(NSE|BSE)$/i.test(exchange.trim())
      ? exchange.trim().toUpperCase()
      : undefined
    let active = true
    setSymbolOptionsLoading(true)
    setSymbolOptionsError(null)
    const id = window.setTimeout(() => {
      void (async () => {
        try {
          const res = await searchMarketSymbols({
            q,
            exchange: exchangeFilter,
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
	  }, [exchange, open, targetKind, targetRef])

    useEffect(() => {
      if (!open) return
      let active = true
      setStrategiesLoading(true)
      setStrategiesError(null)
      void (async () => {
        try {
          const res = await listSignalStrategies({ includeLatest: true, includeUsage: false })
          if (!active) return
          setStrategies(res)
        } catch (err) {
          if (!active) return
          setStrategies([])
          setStrategiesError(
            err instanceof Error ? err.message : 'Failed to load strategies',
          )
        } finally {
          if (!active) return
          setStrategiesLoading(false)
        }
      })()
      return () => {
        active = false
      }
    }, [open])

    useEffect(() => {
      if (!open) return
      if (selectedStrategyId == null) {
        setStrategyVersions([])
        return
      }
      let active = true
      void (async () => {
        try {
          const res = await listSignalStrategyVersions(selectedStrategyId)
          if (!active) return
          setStrategyVersions(res)
          if (res.length > 0) {
            const desired = selectedStrategyVersionId
            const exists = desired != null && res.some((v) => v.id === desired)
            if (!exists) setSelectedStrategyVersionId(res[0]!.id)
          }
        } catch (err) {
          if (!active) return
          setStrategyVersions([])
          setStrategiesError(
            err instanceof Error ? err.message : 'Failed to load strategy versions',
          )
        }
      })()
      return () => {
        active = false
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, selectedStrategyId])

  useEffect(() => {
    if (!open) return
    setError(null)
    if (!alert) {
      setName('')
      setBrokerName(brokers[0]?.name ?? 'zerodha')
      if (createDefaults?.targetKind === 'SYMBOL' && createDefaults.targetRef) {
        setTargetKind('SYMBOL')
        setTargetRef(createDefaults.targetRef)
        setExchange(createDefaults.exchange || 'NSE')
      } else {
        setTargetKind('HOLDINGS')
        setTargetRef('')
        setExchange('NSE')
      }
      setActionType('ALERT_ONLY')
      setActionTab(0)
      setTradeExecutionMode('MANUAL')
      setTradeExecutionTarget('LIVE')
      setTradeSizeMode('QTY')
      setTradeQty('')
      setTradeAmount('')
      setTradePctPosition('')
      setTradeOrderType('MARKET')
      setTradePrice('')
      setTradeTriggerPrice('')
      setTradeProduct('CNC')
      setTradeBracketEnabled(false)
      setTradeMtpPct('')
      setTradeGtt(false)
      setEvaluationCadence('')
      setVariables([])
      setConditionDsl('')
      setTriggerMode('ONCE_PER_BAR')
      setThrottleSeconds('')
      setOnlyMarketHours(false)
      setExpiresAt('')
	      setEnabled(true)
	      setConditionTab(0)
	      setConditionJoin('AND')
	      setConditionRows([{ lhs: '', op: '>', rhs: '' }])
        setUseSavedStrategy(false)
        setSelectedStrategyId(null)
        setStrategyVersions([])
        setSelectedStrategyVersionId(null)
        setSelectedStrategyOutput(null)
        setStrategyParams({})
	      return
	    }
    setName(alert.name)
    setBrokerName(alert.broker_name ?? brokers[0]?.name ?? 'zerodha')
    setTargetKind(alert.target_kind as any)
    if (alert.target_kind === 'SYMBOL') {
      setTargetRef((alert.symbol ?? alert.target_ref).toString())
    } else if (alert.target_kind === 'GROUP') {
      setTargetRef(alert.target_ref)
    } else {
      setTargetRef('')
    }
    setExchange((alert.exchange ?? 'NSE').toString())
    setActionType(
      alert.action_type === 'BUY' || alert.action_type === 'SELL'
        ? alert.action_type
        : 'ALERT_ONLY',
    )
    setActionTab(0)
    setTradeExecutionMode(
      (alert.action_params?.mode ?? 'MANUAL') === 'AUTO' ? 'AUTO' : 'MANUAL',
    )
    setTradeExecutionTarget(
      (alert.action_params?.execution_target ?? 'LIVE') === 'PAPER'
        ? 'PAPER'
        : 'LIVE',
    )
    setTradeSizeMode(
      alert.action_params?.size_mode === 'AMOUNT'
        ? 'AMOUNT'
        : alert.action_params?.size_mode === 'PCT_POSITION'
          ? 'PCT_POSITION'
          : 'QTY',
    )
    setTradeQty(String(alert.action_params?.qty ?? ''))
    setTradeAmount(String(alert.action_params?.amount ?? ''))
    setTradePctPosition(String(alert.action_params?.pct_position ?? ''))
    setTradeOrderType(
      alert.action_params?.order_type === 'LIMIT'
        ? 'LIMIT'
        : alert.action_params?.order_type === 'SL'
          ? 'SL'
          : alert.action_params?.order_type === 'SL-M'
            ? 'SL-M'
            : 'MARKET',
    )
    setTradePrice(String(alert.action_params?.price ?? ''))
    setTradeTriggerPrice(String(alert.action_params?.trigger_price ?? ''))
    setTradeProduct(alert.action_params?.product === 'MIS' ? 'MIS' : 'CNC')
    setTradeBracketEnabled(Boolean(alert.action_params?.bracket_enabled))
    setTradeMtpPct(String(alert.action_params?.mtp_pct ?? ''))
    setTradeGtt(Boolean(alert.action_params?.gtt))
    setEvaluationCadence(alert.evaluation_cadence ?? '')
    setVariables(alert.variables ?? [])
    setConditionDsl(alert.condition_dsl)
    setTriggerMode(alert.trigger_mode)
    setThrottleSeconds(alert.throttle_seconds != null ? String(alert.throttle_seconds) : '')
    setOnlyMarketHours(alert.only_market_hours)
    setExpiresAt(alert.expires_at ?? '')
	    setEnabled(alert.enabled)
	    setConditionTab(1)
	    setConditionJoin('AND')
	    setConditionRows([{ lhs: '', op: '>', rhs: '' }])
      setUseSavedStrategy(false)
      setSelectedStrategyId(null)
      setStrategyVersions([])
      setSelectedStrategyVersionId(null)
      setSelectedStrategyOutput(null)
      setStrategyParams({})
	  }, [open, alert, brokers, createDefaults])

    useEffect(() => {
      if (!open) return
      const vid = (alert?.signal_strategy_version_id ?? null) as number | null
      if (vid == null) return

      setUseSavedStrategy(true)
      setSelectedStrategyVersionId(vid)
      setSelectedStrategyOutput(alert?.signal_strategy_output ?? null)
      setStrategyParams(alert?.signal_strategy_params ?? {})

      void (async () => {
        try {
          const v = await getSignalStrategyVersion(vid)
          setSelectedStrategyId(v.strategy_id)
        } catch {
          // ignore: user can still select manually
        }
      })()
    }, [alert?.id, open])

  useEffect(() => {
    if (actionType === 'ALERT_ONLY') setActionTab(0)
  }, [actionType])

  useEffect(() => {
    // Mirror holdings dialog behavior: only one sizing field is active.
    if (tradeSizeMode === 'QTY') {
      setTradeAmount('')
      setTradePctPosition('')
    } else if (tradeSizeMode === 'AMOUNT') {
      setTradeQty('')
      setTradePctPosition('')
    } else if (tradeSizeMode === 'PCT_POSITION') {
      setTradeQty('')
      setTradeAmount('')
    }
  }, [tradeSizeMode])

  useEffect(() => {
    // Keep price inputs coherent with order type.
    if (tradeOrderType === 'MARKET') {
      setTradePrice('')
      setTradeTriggerPrice('')
    }
    if (tradeOrderType !== 'LIMIT') {
      setTradeGtt(false)
    }
  }, [tradeOrderType])

  const variableKindOf = (v: AlertVariableDef): VariableKind => {
    if (v.kind) return v.kind as VariableKind
    return 'DSL'
  }

  const varParams = (v: AlertVariableDef): Record<string, any> => {
    return (v.params ?? {}) as Record<string, any>
  }

	  const setVariableKind = (idx: number, kind: VariableKind) => {
      if (useSavedStrategy) return
	    setVariables((prev) =>
	      prev.map((v, i) => {
        if (i !== idx) return v
        const name = v.name
        if (kind === 'DSL') return { name, dsl: v.dsl ?? '' }
        if (kind === 'METRIC') return { name, kind: 'METRIC', params: { metric: ALERT_V3_METRICS[0] } }
        if (
          kind === 'PRICE' ||
          kind === 'OPEN' ||
          kind === 'HIGH' ||
          kind === 'LOW' ||
          kind === 'CLOSE' ||
          kind === 'VOLUME'
        ) {
          return { name, kind, params: { timeframe: '1d' } }
        }
        if (kind === 'SMA' || kind === 'EMA' || kind === 'RSI' || kind === 'STDDEV') {
          return { name, kind, params: { source: 'close', length: 14, timeframe: '1d' } }
        }
        if (kind === 'RET') return { name, kind: 'RET', params: { source: 'close', timeframe: '1d' } }
        if (kind === 'ATR') return { name, kind: 'ATR', params: { length: 14, timeframe: '1d' } }
        if (kind === 'OBV') return { name, kind: 'OBV', params: { source: 'close', timeframe: '1d' } }
        if (kind === 'VWAP') return { name, kind: 'VWAP', params: { price: 'hlc3', timeframe: '1d' } }
        if (kind === 'CUSTOM') return { name, kind: 'CUSTOM', params: { function: '', args: [] } }
        return v
      }),
    )
  }

	  const operandOptions = useMemo(() => {
	    const vars = variables
	      .map((v) => (v.name || '').trim())
	      .filter((x) => x.length > 0)
	    return Array.from(new Set([...vars, ...ALERT_V3_METRICS]))
	  }, [variables])

    const activeStrategyVersion = useMemo(() => {
      if (selectedStrategyVersionId == null) return null
      return strategyVersions.find((v) => v.id === selectedStrategyVersionId) ?? null
    }, [selectedStrategyVersionId, strategyVersions])

    useEffect(() => {
      if (!open) return
      if (!useSavedStrategy) return
      if (!activeStrategyVersion) return
      setVariables(activeStrategyVersion.variables ?? [])
      setConditionTab(1)

      const signalOutputs = (activeStrategyVersion.outputs ?? []).filter(
        (o) => String(o.kind || '').toUpperCase() === 'SIGNAL',
      )
      const defaultOutput = signalOutputs[0]?.name ?? null
      if (!selectedStrategyOutput && defaultOutput) {
        setSelectedStrategyOutput(defaultOutput)
      }

      // Initialize params with defaults + current values (if any).
      setStrategyParams((prev) => {
        const next: Record<string, unknown> = {}
        for (const inp of activeStrategyVersion.inputs ?? []) {
          if (!inp?.name) continue
          if (inp.default != null) next[inp.name] = inp.default
        }
        for (const [k, v] of Object.entries(prev || {})) {
          next[k] = v
        }
        return next
      })
    }, [activeStrategyVersion?.id, open, useSavedStrategy, selectedStrategyOutput])

    useEffect(() => {
      if (!open) return
      if (!useSavedStrategy) return
      if (!activeStrategyVersion) return

      const signalOutputs = (activeStrategyVersion.outputs ?? []).filter(
        (o) => String(o.kind || '').toUpperCase() === 'SIGNAL',
      )
      const resolvedName =
        signalOutputs.find((o) => o.name === selectedStrategyOutput)?.name ??
        signalOutputs[0]?.name ??
        null
      const outDsl =
        signalOutputs.find((o) => o.name === resolvedName)?.dsl ??
        signalOutputs[0]?.dsl ??
        ''
      setConditionDsl(String(outDsl || ''))
    }, [activeStrategyVersion?.id, open, selectedStrategyOutput, useSavedStrategy])

  const buildConditionDsl = (): { dsl: string; errors: string[] } => {
    const errors: string[] = []
    const parts: string[] = []

    for (const [idx, row] of conditionRows.entries()) {
      const lhs = (row.lhs || '').trim()
      const rhs = (row.rhs || '').trim()
      if (!lhs || !rhs) continue
      if ((row.op === 'MOVING_UP' || row.op === 'MOVING_DOWN') && Number.isNaN(Number(rhs))) {
        errors.push(`Row ${idx + 1}: MOVING_* RHS must be a number.`)
      }
      parts.push(`(${lhs} ${row.op} ${rhs})`)
    }

    const dsl = parts.join(` ${conditionJoin} `)
    if (!dsl) errors.push('Add at least one complete condition row.')
    return { dsl, errors }
  }

  const conditionPreview = useMemo(
    () => buildConditionDsl(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [conditionRows, conditionJoin],
  )

	  const handleSave = async () => {
	    setSaving(true)
	    setError(null)
	    try {
	      if (useSavedStrategy && selectedStrategyVersionId == null) {
	        throw new Error('Select a saved strategy (and version) before saving.')
	      }
	      const effectiveConditionDsl =
	        conditionTab === 0 ? conditionPreview.dsl.trim() : conditionDsl.trim()
      if (conditionTab === 0 && conditionPreview.errors.length > 0) {
        throw new Error(conditionPreview.errors.join(' '))
      }
      const actionParams =
        actionType === 'ALERT_ONLY'
          ? {}
          : {
              mode: tradeExecutionMode,
              execution_target: tradeExecutionTarget,
              size_mode: tradeSizeMode,
              qty: tradeQty.trim() ? Number(tradeQty) : null,
              amount: tradeAmount.trim() ? Number(tradeAmount) : null,
              pct_position: tradePctPosition.trim() ? Number(tradePctPosition) : null,
              order_type: tradeOrderType,
              price: tradePrice.trim() ? Number(tradePrice) : null,
              trigger_price: tradeTriggerPrice.trim()
                ? Number(tradeTriggerPrice)
                : null,
              product: tradeProduct,
              bracket_enabled: tradeBracketEnabled,
              mtp_pct: tradeMtpPct.trim() ? Number(tradeMtpPct) : null,
              gtt: tradeGtt,
            }
	      const payloadBase: AlertDefinitionCreate = {
	        name: name.trim() || 'Untitled alert',
	        broker_name: brokerName,
	        target_kind: targetKind,
	        target_ref: targetKind === 'GROUP' ? targetRef : null,
	        symbol: targetKind === 'SYMBOL' ? targetRef.trim().toUpperCase() : null,
	        exchange: targetKind === 'SYMBOL' ? exchange : null,
	        action_type: actionType,
	        action_params: actionParams,
	        evaluation_cadence: evaluationCadence.trim() || null,
	        variables,
	        condition_dsl: effectiveConditionDsl,
	        signal_strategy_version_id: useSavedStrategy ? selectedStrategyVersionId : null,
	        signal_strategy_output: useSavedStrategy ? selectedStrategyOutput : null,
	        signal_strategy_params: useSavedStrategy ? strategyParams : {},
	        trigger_mode: triggerMode,
	        throttle_seconds: throttleSeconds.trim() ? Number(throttleSeconds) : null,
	        only_market_hours: onlyMarketHours,
	        expires_at: expiresAt.trim() ? expiresAt : null,
	        enabled,
	      }

      if (!payloadBase.condition_dsl) {
        throw new Error('Condition DSL cannot be empty.')
      }

      if (alert) {
        const update: AlertDefinitionUpdate = payloadBase
        await updateAlertDefinition(alert.id, update)
      } else {
        await createAlertDefinition(payloadBase)
      }

      onClose()
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save alert')
    } finally {
      setSaving(false)
    }
  }

	  const updateVar = (idx: number, next: AlertVariableDef) => {
      if (useSavedStrategy) return
	    setVariables((prev) => prev.map((v, i) => (i === idx ? next : v)))
	  }

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle
        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
      >
        <span>{alert ? 'Edit alert' : 'Create alert'}</span>
        <Tooltip title="Help: DSL syntax, functions, metrics">
          <IconButton size="small" onClick={() => setHelpOpen(true)}>
            <HelpOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <TextField
          label="Name"
          size="small"
          fullWidth
          value={name}
          onChange={(e) => setName(e.target.value)}
          sx={{ mb: 2 }}
        />
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 2 }}>
          <TextField
            label="Broker"
            select
            size="small"
            value={brokerName}
            onChange={(e) => setBrokerName(e.target.value)}
            sx={{ minWidth: 200 }}
          >
            {brokers.length > 0 ? (
              brokers.map((b) => (
                <MenuItem key={b.name} value={b.name}>
                  {b.label}
                </MenuItem>
              ))
            ) : (
              <MenuItem value="zerodha">Zerodha (Kite)</MenuItem>
            )}
          </TextField>
          <TextField
            label="Target kind"
            select
            size="small"
            value={targetKind}
            onChange={(e) => {
              const v = e.target.value as any
              setTargetKind(v)
              if (v === 'HOLDINGS') setTargetRef('')
            }}
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="HOLDINGS">Holdings</MenuItem>
            <MenuItem value="GROUP">Group</MenuItem>
            <MenuItem value="SYMBOL">Single symbol</MenuItem>
          </TextField>
          {targetKind === 'SYMBOL' && (
            <>
              <Autocomplete
                options={symbolOptions}
                loading={symbolOptionsLoading}
                freeSolo
                value={
                  symbolOptions.find(
                    (o) =>
                      o.symbol.toUpperCase() === targetRef.trim().toUpperCase()
                      && o.exchange.toUpperCase() === exchange.trim().toUpperCase(),
                  )
                    ?? (targetRef.trim() ? targetRef.trim().toUpperCase() : null)
                }
                onChange={(_e, value) => {
                  if (typeof value === 'string') {
                    setTargetRef(value.toUpperCase())
                    return
                  }
                  if (value) {
                    setTargetRef(value.symbol.toUpperCase())
                    setExchange(value.exchange.toUpperCase())
                  } else {
                    setTargetRef('')
                  }
                }}
                onInputChange={(_e, value) => setTargetRef(value.toUpperCase())}
                getOptionLabel={(o) => {
                  if (typeof o === 'string') return o
                  return `${o.symbol} (${o.exchange})`
                }}
                isOptionEqualToValue={(a, b) => {
                  if (typeof b === 'string') return a.symbol === b
                  return a.symbol === b.symbol && a.exchange === b.exchange
                }}
                renderOption={(props, option) => (
                  <li {...props}>
                    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                      <Typography variant="body2">
                        {option.symbol} ({option.exchange})
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
                    size="small"
                    sx={{ minWidth: 260 }}
                    helperText={symbolOptionsError ?? 'Start typing to search symbols.'}
                  />
                )}
              />
              <TextField
                label="Exchange"
                size="small"
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                sx={{ minWidth: 140 }}
              />
            </>
          )}
          {targetKind === 'GROUP' && (
            <Autocomplete
              options={groups}
              value={
                groups.find((g) => String(g.id) === String(targetRef).trim()) ?? null
              }
              onChange={(_e, value) => setTargetRef(value ? String(value.id) : '')}
              getOptionLabel={(o) => `${o.name} (#${o.id})`}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              renderOption={(props, option) => (
                <li {...props}>
                  <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="body2">
                      {option.name} (#{option.id})
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {option.kind} • {option.member_count} members
                    </Typography>
                  </Box>
                </li>
              )}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Group"
                  size="small"
                  sx={{ minWidth: 320 }}
                  helperText="Pick an existing group."
                />
              )}
            />
          )}
          <TextField
            label="Cadence (optional)"
            size="small"
            value={evaluationCadence}
            onChange={(e) => setEvaluationCadence(e.target.value)}
            placeholder="auto"
            sx={{ minWidth: 160 }}
          />
          <TextField
            label="Action"
            select
            size="small"
            value={actionType}
            onChange={(e) => {
              const v = e.target.value
              setActionType(v === 'BUY' ? 'BUY' : v === 'SELL' ? 'SELL' : 'ALERT_ONLY')
            }}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="ALERT_ONLY">Alert only</MenuItem>
            <MenuItem value="BUY">Buy</MenuItem>
            <MenuItem value="SELL">Sell</MenuItem>
          </TextField>
        </Box>

        {actionType !== 'ALERT_ONLY' && (
          <Tabs
            value={actionTab}
            onChange={(_e, v) => setActionTab(v as 0 | 1)}
            sx={{ mb: 2 }}
          >
            <Tab label="Condition" />
            <Tab label={actionType === 'BUY' ? 'Buy template' : 'Sell template'} />
          </Tabs>
        )}

	        {(actionType === 'ALERT_ONLY' || actionTab === 0) && (
	          <>
              <Box sx={{ mb: 2 }}>
                <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={useSavedStrategy}
                        onChange={(e) => {
                          const next = e.target.checked
                          setUseSavedStrategy(next)
                          if (!next) return
                          setConditionTab(1)
                        }}
                      />
                    }
                    label="Use saved strategy"
                  />
                  {strategiesError && (
                    <Typography variant="caption" color="error">
                      {strategiesError}
                    </Typography>
                  )}
                </Stack>

                {useSavedStrategy && (
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                      <Autocomplete
                        options={strategies}
                        value={
                          strategies.find((s) => s.id === selectedStrategyId) ?? null
                        }
                        loading={strategiesLoading}
                        onChange={(_e, v) => {
                          setSelectedStrategyId(v?.id ?? null)
                          setSelectedStrategyVersionId(null)
                          setSelectedStrategyOutput(null)
                          setStrategyParams({})
                        }}
                        getOptionLabel={(s) => `${s.name} (v${s.latest_version})`}
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            label="Strategy"
                            size="small"
                            sx={{ minWidth: 360 }}
                          />
                        )}
                      />

                      <TextField
                        label="Version"
                        select
                        size="small"
                        value={selectedStrategyVersionId ?? ''}
                        onChange={(e) => {
                          const n = Number(e.target.value || '')
                          setSelectedStrategyVersionId(Number.isFinite(n) ? n : null)
                          setSelectedStrategyOutput(null)
                        }}
                        sx={{ minWidth: 120 }}
                        disabled={selectedStrategyId == null || strategyVersions.length === 0}
                      >
                        {strategyVersions.map((v) => (
                          <MenuItem key={v.id} value={v.id}>
                            v{v.version}
                          </MenuItem>
                        ))}
                      </TextField>

                      <TextField
                        label="Signal output"
                        select
                        size="small"
                        value={selectedStrategyOutput ?? ''}
                        onChange={(e) => setSelectedStrategyOutput(e.target.value || null)}
                        sx={{ minWidth: 180 }}
                        disabled={
                          !activeStrategyVersion ||
                          (activeStrategyVersion.outputs ?? []).filter(
                            (o) => String(o.kind || '').toUpperCase() === 'SIGNAL',
                          ).length === 0
                        }
                      >
                        {(activeStrategyVersion?.outputs ?? [])
                          .filter((o) => String(o.kind || '').toUpperCase() === 'SIGNAL')
                          .map((o) => (
                            <MenuItem key={o.name} value={o.name}>
                              {o.name}
                            </MenuItem>
                          ))}
                      </TextField>
                    </Stack>

                    {(activeStrategyVersion?.inputs ?? []).length > 0 && (
                      <Box>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                          Strategy parameters
                        </Typography>
                        <Stack spacing={1}>
                          {(activeStrategyVersion?.inputs ?? []).map((inp) => {
                            const key = inp.name
                            const raw = strategyParams[key]
                            const val = raw == null ? '' : String(raw)
                            const typ = inp.type
                            const enumValues = Array.isArray(inp.enum_values) ? inp.enum_values : []
                            return (
                              <Stack key={key} direction="row" spacing={1} alignItems="center">
                                <TextField
                                  label={key}
                                  size="small"
                                  value={val}
                                  onChange={(e) => {
                                    const nextRaw = e.target.value
                                    const nextVal =
                                      typ === 'number'
                                        ? (Number.isFinite(Number(nextRaw)) ? Number(nextRaw) : nextRaw)
                                        : typ === 'bool'
                                          ? nextRaw === 'true'
                                          : nextRaw
                                    setStrategyParams((prev) => ({ ...prev, [key]: nextVal }))
                                  }}
                                  select={typ === 'bool' || (typ === 'enum' && enumValues.length > 0)}
                                  sx={{ minWidth: 220 }}
                                >
                                  {typ === 'bool' ? (
                                    [
                                      <MenuItem key="true" value="true">
                                        true
                                      </MenuItem>,
                                      <MenuItem key="false" value="false">
                                        false
                                      </MenuItem>,
                                    ]
                                  ) : null}
                                  {typ === 'enum' && enumValues.length > 0
                                    ? enumValues.map((ev) => (
                                        <MenuItem key={ev} value={ev}>
                                          {ev}
                                        </MenuItem>
                                      ))
                                    : null}
                                </TextField>
                                {inp.default != null && (
                                  <Typography variant="caption" color="text.secondary">
                                    default: {String(inp.default)}
                                  </Typography>
                                )}
                              </Stack>
                            )
                          })}
                        </Stack>
                      </Box>
                    )}
                  </Stack>
                )}
              </Box>

	            <Typography variant="subtitle2" sx={{ mb: 1 }}>
	              Variables (optional)
	            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Provide readable aliases like <code>RSI_1H_14</code> = <code>RSI(close, 14, &quot;1h&quot;)</code>.
            </Typography>
	            <Box
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1,
                  mb: 2,
                  pointerEvents: useSavedStrategy ? 'none' : 'auto',
                  opacity: useSavedStrategy ? 0.7 : 1,
                }}
              >
              {variables.map((v, idx) => (
                <Box key={idx} sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'flex-start' }}>
              <TextField
                label="Name"
                size="small"
                value={v.name}
                onChange={(e) =>
                  updateVar(idx, { ...v, name: e.target.value })
                }
                sx={{ width: 200 }}
              />
              <TextField
                label="Type"
                select
                size="small"
                value={variableKindOf(v)}
                onChange={(e) =>
                  setVariableKind(idx, e.target.value as any)
                }
                sx={{ width: 190 }}
              >
                <MenuItem value="DSL">DSL (advanced)</MenuItem>
                <MenuItem value="METRIC">Metric</MenuItem>
                <MenuItem value="PRICE">Price (close)</MenuItem>
                <MenuItem value="OPEN">Open</MenuItem>
                <MenuItem value="HIGH">High</MenuItem>
                <MenuItem value="LOW">Low</MenuItem>
                <MenuItem value="CLOSE">Close</MenuItem>
                <MenuItem value="VOLUME">Volume</MenuItem>
                <MenuItem value="SMA">SMA</MenuItem>
                <MenuItem value="EMA">EMA</MenuItem>
                <MenuItem value="RSI">RSI</MenuItem>
                <MenuItem value="STDDEV">StdDev</MenuItem>
                <MenuItem value="RET">Return</MenuItem>
                <MenuItem value="ATR">ATR</MenuItem>
                <MenuItem value="OBV">OBV</MenuItem>
                <MenuItem value="VWAP">VWAP</MenuItem>
                <MenuItem value="CUSTOM">Custom indicator</MenuItem>
              </TextField>
              {variableKindOf(v) === 'DSL' && (
                <TextField
                  label="DSL"
                  size="small"
                  value={v.dsl ?? ''}
                  onChange={(e) => updateVar(idx, { ...v, dsl: e.target.value })}
                  sx={{ flex: 1, minWidth: 260 }}
                />
              )}
              {variableKindOf(v) === 'METRIC' && (
                <TextField
                  label="Metric"
                  select
                  size="small"
                  value={String(varParams(v).metric ?? ALERT_V3_METRICS[0])}
                  onChange={(e) =>
                    updateVar(idx, { ...v, kind: 'METRIC', params: { metric: e.target.value } })
                  }
                  sx={{ minWidth: 240 }}
                >
                  {ALERT_V3_METRICS.map((m) => (
                    <MenuItem key={m} value={m}>
                      {m}
                    </MenuItem>
                  ))}
                </TextField>
              )}
              {['PRICE', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME'].includes(variableKindOf(v)) && (
                <TextField
                  label="Timeframe"
                  select
                  size="small"
                  value={String(varParams(v).timeframe ?? '1d')}
                  onChange={(e) =>
                    updateVar(idx, {
                      ...v,
                      kind: variableKindOf(v) as any,
                      params: { timeframe: e.target.value },
                    })
                  }
                  sx={{ minWidth: 160 }}
                >
                  {ALERT_V3_TIMEFRAMES.map((tf) => (
                    <MenuItem key={tf} value={tf}>
                      {tf}
                    </MenuItem>
                  ))}
                </TextField>
              )}
              {['SMA', 'EMA', 'RSI', 'STDDEV'].includes(
                variableKindOf(v),
              ) && (
                <>
                  <TextField
                    label="Source"
                    select
                    size="small"
                    value={String(varParams(v).source ?? 'close')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: variableKindOf(v) as any,
                        params: { ...varParams(v), source: e.target.value },
                      })
                    }
                    sx={{ minWidth: 140 }}
                  >
                    {ALERT_V3_SOURCES.map((s) => (
                      <MenuItem key={s} value={s}>
                        {s}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Length"
                    size="small"
                    type="number"
                    value={String(varParams(v).length ?? 14)}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: variableKindOf(v) as any,
                        params: { ...varParams(v), length: Number(e.target.value) || 0 },
                      })
                    }
                    sx={{ width: 120 }}
                  />
                  <TextField
                    label="Timeframe"
                    select
                    size="small"
                    value={String(varParams(v).timeframe ?? '1d')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: variableKindOf(v) as any,
                        params: { ...varParams(v), timeframe: e.target.value },
                      })
                    }
                    sx={{ width: 140 }}
                  >
                    {ALERT_V3_TIMEFRAMES.map((tf) => (
                      <MenuItem key={tf} value={tf}>
                        {tf}
                      </MenuItem>
                    ))}
                  </TextField>
                </>
              )}
              {variableKindOf(v) === 'OBV' && (
                <>
                  <TextField
                    label="Close source"
                    select
                    size="small"
                    value={String(varParams(v).source ?? 'close')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'OBV',
                        params: { ...varParams(v), source: e.target.value },
                      })
                    }
                    sx={{ minWidth: 160 }}
                  >
                    {['close', 'hlc3'].map((s) => (
                      <MenuItem key={s} value={s}>
                        {s}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Timeframe"
                    select
                    size="small"
                    value={String(varParams(v).timeframe ?? '1d')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'OBV',
                        params: { ...varParams(v), timeframe: e.target.value },
                      })
                    }
                    sx={{ width: 140 }}
                  >
                    {ALERT_V3_TIMEFRAMES.map((tf) => (
                      <MenuItem key={tf} value={tf}>
                        {tf}
                      </MenuItem>
                    ))}
                  </TextField>
                </>
              )}
              {variableKindOf(v) === 'VWAP' && (
                <>
                  <TextField
                    label="Price"
                    select
                    size="small"
                    value={String(varParams(v).price ?? 'hlc3')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'VWAP',
                        params: { ...varParams(v), price: e.target.value },
                      })
                    }
                    sx={{ minWidth: 160 }}
                  >
                    {['hlc3', 'close', 'open', 'high', 'low'].map((s) => (
                      <MenuItem key={s} value={s}>
                        {s}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Timeframe"
                    select
                    size="small"
                    value={String(varParams(v).timeframe ?? '1d')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'VWAP',
                        params: { ...varParams(v), timeframe: e.target.value },
                      })
                    }
                    sx={{ width: 140 }}
                  >
                    {ALERT_V3_TIMEFRAMES.map((tf) => (
                      <MenuItem key={tf} value={tf}>
                        {tf}
                      </MenuItem>
                    ))}
                  </TextField>
                </>
              )}
              {variableKindOf(v) === 'RET' && (
                <>
                  <TextField
                    label="Source"
                    select
                    size="small"
                    value={String(varParams(v).source ?? 'close')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'RET',
                        params: { ...varParams(v), source: e.target.value },
                      })
                    }
                    sx={{ minWidth: 140 }}
                  >
                    {ALERT_V3_SOURCES.map((s) => (
                      <MenuItem key={s} value={s}>
                        {s}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Timeframe"
                    select
                    size="small"
                    value={String(varParams(v).timeframe ?? '1d')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'RET',
                        params: { ...varParams(v), timeframe: e.target.value },
                      })
                    }
                    sx={{ width: 140 }}
                  >
                    {ALERT_V3_TIMEFRAMES.map((tf) => (
                      <MenuItem key={tf} value={tf}>
                        {tf}
                      </MenuItem>
                    ))}
                  </TextField>
                </>
              )}
              {variableKindOf(v) === 'ATR' && (
                <>
                  <TextField
                    label="Length"
                    size="small"
                    type="number"
                    value={String(varParams(v).length ?? 14)}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'ATR',
                        params: { ...varParams(v), length: Number(e.target.value) || 0 },
                      })
                    }
                    sx={{ width: 120 }}
                  />
                  <TextField
                    label="Timeframe"
                    select
                    size="small"
                    value={String(varParams(v).timeframe ?? '1d')}
                    onChange={(e) =>
                      updateVar(idx, {
                        ...v,
                        kind: 'ATR',
                        params: { ...varParams(v), timeframe: e.target.value },
                      })
                    }
                    sx={{ width: 140 }}
                  >
                    {ALERT_V3_TIMEFRAMES.map((tf) => (
                      <MenuItem key={tf} value={tf}>
                        {tf}
                      </MenuItem>
                    ))}
                  </TextField>
                </>
              )}
              {variableKindOf(v) === 'CUSTOM' && (
                <>
                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                    <Autocomplete
                      options={customIndicators}
                      loading={customIndicatorsLoading}
                      value={
                        customIndicators.find(
                          (ci) =>
                            ci.name.toUpperCase() ===
                            String(varParams(v).function ?? '').toUpperCase(),
                        ) ?? null
                      }
                      onChange={(_e, value) =>
                        updateVar(idx, {
                          ...v,
                          kind: 'CUSTOM',
                          params: { ...varParams(v), function: value?.name ?? '' },
                        })
                      }
                      getOptionLabel={(o) => o.name}
                      isOptionEqualToValue={(a, b) => a.id === b.id}
                      renderOption={(props, option) => (
                        <li {...props}>
                          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                            <Typography variant="body2">
                              {option.name}
                              {option.params?.length
                                ? `(${option.params.join(', ')})`
                                : ''}
                            </Typography>
                            {option.description ? (
                              <Typography variant="caption" color="text.secondary">
                                {option.description}
                              </Typography>
                            ) : null}
                          </Box>
                        </li>
                      )}
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="Function"
                          size="small"
                          sx={{ minWidth: 260 }}
                          helperText={
                            customIndicatorsError
                              ? customIndicatorsError
                              : !customIndicatorsLoading && customIndicators.length === 0
                                ? 'No custom indicators yet.'
                                : undefined
                          }
                        />
                      )}
                    />
                    <Tooltip title="Refresh indicators">
                      <span>
                        <IconButton
                          size="small"
                          onClick={() => void refreshCustomIndicators()}
                          disabled={customIndicatorsLoading}
                        >
                          <RefreshIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Button
                      size="small"
                      variant="text"
                      onClick={() =>
                        window.open(
                          '/alerts?tab=indicators',
                          '_blank',
                          'noopener,noreferrer',
                        )
                      }
                    >
                      Add new indicator
                    </Button>
                  </Box>
                  <TextField
                    label="Args (comma-separated DSL)"
                    size="small"
                    value={(Array.isArray(varParams(v).args) ? varParams(v).args : []).join(', ')}
                    onChange={(e) => {
                      const args = e.target.value
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean)
                      updateVar(idx, {
                        ...v,
                        kind: 'CUSTOM',
                        params: { ...varParams(v), args },
                      })
                    }}
                    sx={{ minWidth: 280, flex: 1 }}
                  />
                </>
              )}
              <Button
                color="error"
                onClick={() =>
                  setVariables((prev) => prev.filter((_x, i) => i !== idx))
                }
              >
                Remove
              </Button>
            </Box>
          ))}
          <Button
            variant="outlined"
            onClick={() =>
              setVariables((prev) => [...prev, { name: '', dsl: '' }])
            }
          >
            Add variable
          </Button>
        </Box>

            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Condition
            </Typography>
	            <Tabs
	              value={conditionTab}
	              onChange={(_e, v) => {
                  if (useSavedStrategy) return
                  setConditionTab(v as 0 | 1)
                }}
	              sx={{ mb: 1 }}
	            >
	              <Tab label="Builder" disabled={useSavedStrategy} />
	              <Tab label="Advanced (DSL)" />
	            </Tabs>

            {conditionTab === 0 && (
              <Box sx={{ mb: 2 }}>
                <Box
                  sx={{
                    display: 'flex',
                    gap: 2,
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    mb: 1,
                  }}
                >
                  <TextField
                    label="Match mode"
                    select
                    size="small"
                    value={conditionJoin}
                    onChange={(e) => setConditionJoin(e.target.value as any)}
                    sx={{ minWidth: 220 }}
                  >
                    <MenuItem value="AND">All conditions (AND)</MenuItem>
                    <MenuItem value="OR">Any condition (OR)</MenuItem>
                  </TextField>
                  <Button
                    variant="outlined"
                    onClick={() =>
                      setConditionRows((prev) => [
                        ...prev,
                        { lhs: '', op: '>', rhs: '' },
                      ])
                    }
                  >
                    + Add condition
                  </Button>
                </Box>

                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {conditionRows.map((row, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        display: 'flex',
                        gap: 1,
                        flexWrap: 'wrap',
                        alignItems: 'center',
                      }}
                    >
                      <Autocomplete
                        freeSolo
                        options={operandOptions}
                        value={row.lhs}
                        onChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, lhs: String(v ?? '') } : r,
                            ),
                          )
                        }
                        onInputChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, lhs: v } : r,
                            ),
                          )
                        }
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            label="LHS"
                            size="small"
                            sx={{ width: 240 }}
                          />
                        )}
                      />
                      <TextField
                        label="Operator"
                        select
                        size="small"
                        value={row.op}
                        onChange={(e) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) =>
                              i === idx
                                ? { ...r, op: e.target.value as any }
                                : r,
                            ),
                          )
                        }
                        sx={{ width: 170 }}
                      >
                        <MenuItem value=">">&gt;</MenuItem>
                        <MenuItem value=">=">&gt;=</MenuItem>
                        <MenuItem value="<">&lt;</MenuItem>
                        <MenuItem value="<=">&lt;=</MenuItem>
                        <MenuItem value="==">==</MenuItem>
                        <MenuItem value="!=">!=</MenuItem>
                        <MenuItem value="CROSSES_ABOVE">CROSSES_ABOVE</MenuItem>
                        <MenuItem value="CROSSES_BELOW">CROSSES_BELOW</MenuItem>
                        <MenuItem value="MOVING_UP">MOVING_UP (%)</MenuItem>
                        <MenuItem value="MOVING_DOWN">MOVING_DOWN (%)</MenuItem>
                      </TextField>
                      <Autocomplete
                        freeSolo
                        options={operandOptions}
                        value={row.rhs}
                        onChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, rhs: String(v ?? '') } : r,
                            ),
                          )
                        }
                        onInputChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, rhs: v } : r,
                            ),
                          )
                        }
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            label="RHS"
                            size="small"
                            sx={{ width: 240 }}
                            helperText={
                              row.op === 'MOVING_UP' || row.op === 'MOVING_DOWN'
                                ? 'RHS must be numeric'
                                : undefined
                            }
                          />
                        )}
                      />
                      <Button
                        color="error"
                        onClick={() =>
                          setConditionRows((prev) =>
                            prev.filter((_x, i) => i !== idx),
                          )
                        }
                        disabled={conditionRows.length <= 1}
                      >
                        Remove
                      </Button>
                    </Box>
                  ))}
                </Box>

                <Typography variant="subtitle2" sx={{ mt: 2, mb: 0.5 }}>
                  Expression preview (read-only)
                </Typography>
                <Paper
                  variant="outlined"
                  sx={{ p: 1, bgcolor: 'background.default' }}
                >
                  <Typography
                    component="pre"
                    variant="body2"
                    sx={{ m: 0, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}
                  >
                    {conditionPreview.dsl || '—'}
                  </Typography>
                </Paper>
                {conditionPreview.errors.length > 0 && (
                  <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                    {conditionPreview.errors.join(' ')}
                  </Typography>
                )}
              </Box>
            )}

            {conditionTab === 1 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  Condition DSL
                </Typography>
                <DslEditor
                  languageId="st-dsl-alerts-condition"
                  value={conditionDsl}
                  onChange={setConditionDsl}
                  operands={operandOptions}
                  customIndicators={customIndicators}
                  height={160}
                />
                <Typography variant="caption" color="text.secondary">
                  Example: <code>RSI_1H_14 &lt; 30 AND TODAY_PNL_PCT &gt; 5</code> — press{' '}
                  <code>Tab</code> to accept a suggestion/snippet.
                </Typography>
              </Box>
            )}

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 1 }}>
              <TextField
                label="Trigger mode"
                select
                size="small"
                value={triggerMode}
                onChange={(e) => setTriggerMode(e.target.value as any)}
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="ONCE">Only once</MenuItem>
                <MenuItem value="ONCE_PER_BAR">Once per bar</MenuItem>
                <MenuItem value="EVERY_TIME">Every time</MenuItem>
              </TextField>
              <TextField
                label="Throttle seconds (optional)"
                size="small"
                value={throttleSeconds}
                onChange={(e) => setThrottleSeconds(e.target.value)}
                sx={{ minWidth: 220 }}
              />
              <TextField
                label="Expires at (optional)"
                size="small"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                placeholder="YYYY-MM-DDTHH:MM:SS"
                sx={{ minWidth: 260 }}
              />
            </Box>
            <Box sx={{ display: 'flex', gap: 3 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={onlyMarketHours}
                    onChange={(e) => setOnlyMarketHours(e.target.checked)}
                  />
                }
                label="Only market hours"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={enabled}
                    onChange={(e) => setEnabled(e.target.checked)}
                  />
                }
                label={enabled ? 'Enabled' : 'Paused'}
              />
            </Box>
          </>
        )}

        {actionType !== 'ALERT_ONLY' && actionTab === 1 && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {actionType === 'BUY' ? 'Buy' : 'Sell'} template
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Symbol is resolved at trigger time. This template intentionally excludes symbol-specific fields.
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box
                sx={{
                  display: 'flex',
                  gap: 2,
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <TextField
                  label="Submit mode"
                  select
                  value={tradeExecutionMode}
                  onChange={(e) =>
                    setTradeExecutionMode(
                      e.target.value === 'AUTO' ? 'AUTO' : 'MANUAL',
                    )
                  }
                  size="small"
                  sx={{ minWidth: 240 }}
                  helperText={
                    tradeExecutionMode === 'AUTO'
                      ? 'AUTO sends immediately; may skip the waiting queue.'
                      : 'MANUAL adds orders to the waiting queue.'
                  }
                >
                  <MenuItem value="MANUAL">Manual (review in queue)</MenuItem>
                  <MenuItem value="AUTO">Auto (send now)</MenuItem>
                </TextField>
                <FormControlLabel
                  control={
                    <Switch
                      checked={tradeExecutionTarget === 'PAPER'}
                      onChange={(e) =>
                        setTradeExecutionTarget(e.target.checked ? 'PAPER' : 'LIVE')
                      }
                    />
                  }
                  label={`Execution target: ${tradeExecutionTarget}`}
                />
              </Box>

              <Box>
                <Typography variant="caption" color="text.secondary">
                  Position sizing
                </Typography>
                <RadioGroup
                  row
                  value={tradeSizeMode}
                  onChange={(e) => {
                    const mode =
                      e.target.value === 'AMOUNT'
                        ? 'AMOUNT'
                        : e.target.value === 'PCT_POSITION'
                          ? 'PCT_POSITION'
                          : 'QTY'
                    setTradeSizeMode(mode)
                  }}
                >
                  <FormControlLabel
                    value="QTY"
                    control={<Radio size="small" />}
                    label="Qty"
                  />
                  <FormControlLabel
                    value="AMOUNT"
                    control={<Radio size="small" />}
                    label="Amount"
                  />
                  <FormControlLabel
                    value="PCT_POSITION"
                    control={<Radio size="small" />}
                    label="% of position"
                  />
                </RadioGroup>
              </Box>

              <TextField
                label="Quantity"
                type="number"
                value={tradeQty}
                onChange={(e) => {
                  setTradeSizeMode('QTY')
                  setTradeQty(e.target.value)
                }}
                fullWidth
                size="small"
                disabled={tradeSizeMode !== 'QTY'}
              />
              <TextField
                label="Amount"
                type="number"
                value={tradeAmount}
                onChange={(e) => {
                  setTradeSizeMode('AMOUNT')
                  setTradeAmount(e.target.value)
                }}
                fullWidth
                size="small"
                disabled={tradeSizeMode !== 'AMOUNT'}
              />
              <TextField
                label="% of position"
                type="number"
                value={tradePctPosition}
                onChange={(e) => {
                  setTradeSizeMode('PCT_POSITION')
                  setTradePctPosition(e.target.value)
                }}
                fullWidth
                size="small"
                disabled={tradeSizeMode !== 'PCT_POSITION'}
              />

              <TextField
                label="Order type"
                select
                value={tradeOrderType}
                onChange={(e) =>
                  setTradeOrderType(
                    e.target.value as 'MARKET' | 'LIMIT' | 'SL' | 'SL-M',
                  )
                }
                fullWidth
                size="small"
              >
                <MenuItem value="MARKET">MARKET</MenuItem>
                <MenuItem value="LIMIT">LIMIT</MenuItem>
                <MenuItem value="SL">SL (Stop-loss limit)</MenuItem>
                <MenuItem value="SL-M">SL-M (Stop-loss market)</MenuItem>
              </TextField>

              <TextField
                label="Price"
                type="number"
                value={tradePrice}
                onChange={(e) => setTradePrice(e.target.value)}
                fullWidth
                size="small"
                disabled={tradeOrderType === 'MARKET' || tradeOrderType === 'SL-M'}
              />

              {(tradeOrderType === 'SL' || tradeOrderType === 'SL-M' || tradeGtt) && (
                <TextField
                  label="Trigger price"
                  type="number"
                  value={tradeTriggerPrice}
                  onChange={(e) => setTradeTriggerPrice(e.target.value)}
                  fullWidth
                  size="small"
                  helperText={
                    tradeOrderType === 'SL' || tradeOrderType === 'SL-M'
                      ? 'Required for SL / SL-M orders.'
                      : brokerName === 'zerodha'
                        ? 'Optional trigger for GTT orders; defaults to limit price when left blank.'
                        : 'Optional trigger for conditional orders; defaults to limit price when left blank.'
                  }
                />
              )}

              <TextField
                label="Product"
                select
                value={tradeProduct}
                onChange={(e) =>
                  setTradeProduct(e.target.value === 'MIS' ? 'MIS' : 'CNC')
                }
                fullWidth
                size="small"
                helperText="Select MIS for intraday or CNC for delivery."
              >
                <MenuItem value="CNC">CNC (Delivery)</MenuItem>
                <MenuItem value="MIS">MIS (Intraday)</MenuItem>
              </TextField>

              <Box
                sx={{
                  mt: 1,
                  p: 1,
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1,
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  Bracket / follow-up conditional
                </Typography>
                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={tradeBracketEnabled}
                      onChange={(e) => setTradeBracketEnabled(e.target.checked)}
                    />
                  }
                  label={
                    (() => {
                      const suffix = brokerName === 'zerodha' ? 'GTT' : 'conditional'
                      return actionType === 'BUY'
                        ? `Add profit-target SELL ${suffix}`
                        : `Add re-entry BUY ${suffix}`
                    })()
                  }
                />
                {tradeBracketEnabled && (
                  <TextField
                    label="Min target profit (MTP) %"
                    type="number"
                    value={tradeMtpPct}
                    onChange={(e) => setTradeMtpPct(e.target.value)}
                    size="small"
                    fullWidth
                    helperText="This is evaluated at trigger time using the resolved primary price."
                  />
                )}
              </Box>

              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={tradeGtt}
                    onChange={(e) => setTradeGtt(e.target.checked)}
                    disabled={tradeOrderType !== 'LIMIT'}
                  />
                }
                label={
                  brokerName === 'zerodha'
                    ? 'GTT (good-till-triggered) order'
                    : 'Conditional order (SigmaTrader-managed)'
                }
              />
              {tradeOrderType !== 'LIMIT' && (
                <Typography variant="caption" color="text.secondary">
                  Conditional/GTT is available only for LIMIT orders.
                </Typography>
              )}
            </Box>
          </>
        )}
        {error && (
          <Typography variant="body2" color="error" sx={{ mt: 1 }}>
            {error}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button variant="contained" onClick={() => void handleSave()} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
      <DslHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} context="alerts" />
    </Dialog>
  )
}

function IndicatorsV3Tab() {
  const [rows, setRows] = useState<CustomIndicator[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<CustomIndicator | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      setRows(await listCustomIndicators())
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to load custom indicators',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const columns: GridColDef[] = [
    { field: 'name', headerName: 'Name', flex: 1, minWidth: 220 },
    {
      field: 'params',
      headerName: 'Params',
      width: 220,
      valueGetter: (_v, row) => (row.params ?? []).join(', '),
    },
    {
      field: 'enabled',
      headerName: 'Status',
      width: 110,
      renderCell: (params: GridRenderCellParams<CustomIndicator, boolean>) => (
        <Chip
          size="small"
          label={params.value ? 'Enabled' : 'Disabled'}
          color={params.value ? 'success' : 'default'}
        />
      ),
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 220,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const row = params.row as CustomIndicator
        return (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                setEditing(row)
                setEditorOpen(true)
              }}
            >
              Edit
            </Button>
            <Button
              size="small"
              color="error"
              onClick={async () => {
                const ok = window.confirm(`Delete indicator '${row.name}'?`)
                if (!ok) return
                try {
                  await deleteCustomIndicator(row.id)
                  await refresh()
                } catch (err) {
                  setError(
                    err instanceof Error
                      ? err.message
                      : 'Failed to delete custom indicator',
                  )
                }
              }}
            >
              Delete
            </Button>
          </Box>
        )
      },
    },
  ]

  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Custom indicators are reusable numeric functions used in alert variables/conditions.
      </Typography>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
        <Button
          variant="contained"
          onClick={() => {
            setEditing(null)
            setEditorOpen(true)
          }}
        >
          Create indicator
        </Button>
        <Button variant="outlined" onClick={() => void refresh()} disabled={loading}>
          Refresh
        </Button>
      </Box>
      <Paper sx={{ height: 520, width: '100%' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          density="compact"
          loading={loading}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          initialState={{
            pagination: { paginationModel: { pageSize: 25 } },
          }}
          pageSizeOptions={[25, 50, 100]}
          localeText={{
            noRowsLabel: loading ? 'Loading...' : 'No custom indicators found.',
          }}
        />
      </Paper>
      <CustomIndicatorEditorDialog
        open={editorOpen}
        indicator={editing}
        onClose={() => setEditorOpen(false)}
        onSaved={() => void refresh()}
      />
    </Box>
  )
}

type CustomIndicatorEditorDialogProps = {
  open: boolean
  indicator: CustomIndicator | null
  onClose: () => void
  onSaved: () => void
}

function CustomIndicatorEditorDialog({
  open,
  indicator,
  onClose,
  onSaved,
}: CustomIndicatorEditorDialogProps) {
  const [helpOpen, setHelpOpen] = useState(false)
  const [name, setName] = useState('')
  const [params, setParams] = useState('')
  const [bodyDsl, setBodyDsl] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setError(null)
    if (!indicator) {
      setName('')
      setParams('')
      setBodyDsl('')
      setEnabled(true)
      return
    }
    setName(indicator.name)
    setParams((indicator.params ?? []).join(', '))
    setBodyDsl(indicator.body_dsl)
    setEnabled(indicator.enabled)
  }, [open, indicator])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const paramList = params
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const payload: CustomIndicatorCreate = {
        name: name.trim(),
        params: paramList,
        body_dsl: bodyDsl.trim(),
        enabled,
      }
      if (!payload.name) throw new Error('Name is required.')
      if (!payload.body_dsl) throw new Error('Formula is required.')

      if (indicator) {
        const update: CustomIndicatorUpdate = payload
        await updateCustomIndicator(indicator.id, update)
      } else {
        await createCustomIndicator(payload)
      }

      onClose()
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save indicator')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle
        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
      >
        <span>{indicator ? 'Edit custom indicator' : 'Create custom indicator'}</span>
        <Tooltip title="Help: formula DSL + allowed functions">
          <IconButton size="small" onClick={() => setHelpOpen(true)}>
            <HelpOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <TextField
          label="Name"
          size="small"
          fullWidth
          value={name}
          onChange={(e) => setName(e.target.value)}
          sx={{ mb: 2 }}
        />
        <TextField
          label="Parameters (comma separated)"
          size="small"
          fullWidth
          value={params}
          onChange={(e) => setParams(e.target.value)}
          sx={{ mb: 2 }}
          helperText="Example: src, len_atr, len_vol"
        />
        <TextField
          label="Formula DSL"
          size="small"
          fullWidth
          value={bodyDsl}
          onChange={(e) => setBodyDsl(e.target.value)}
          multiline
          minRows={4}
          helperText='Example: ATR(14, "1d") / PRICE("1d") * 100'
        />
        <FormControlLabel
          sx={{ mt: 1 }}
          control={<Switch checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />}
          label={enabled ? 'Enabled' : 'Disabled'}
        />
        {error && (
          <Typography variant="body2" color="error" sx={{ mt: 1 }}>
            {error}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button variant="contained" onClick={() => void handleSave()} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
      <CustomIndicatorHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </Dialog>
  )
}

function CustomIndicatorHelpDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Custom indicator help</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Custom indicators are reusable numeric formulas. They cannot contain comparisons,
          logical operators (AND/OR/NOT), or event operators (CROSSES_*/MOVING_*). Use them inside
          alert variables/conditions.
        </Typography>

        <Typography variant="subtitle2">Parameters</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Parameters are identifiers you can reference inside the formula. Example params:{' '}
          <code>src</code>, <code>len</code>.
        </Typography>

        <Typography variant="subtitle2">Allowed functions</Typography>
        <Typography variant="body2" component="div" sx={{ mb: 2 }}>
          - <code>OPEN(tf)</code>, <code>HIGH(tf)</code>, <code>LOW(tf)</code>,{' '}
          <code>CLOSE(tf)</code>, <code>VOLUME(tf)</code>, <code>PRICE(tf)</code>,{' '}
          <code>PRICE(source, tf)</code>
          <br />
          - <code>SMA(series, len, tf?)</code>, <code>EMA(series, len, tf?)</code>,{' '}
          <code>RSI(series, len, tf?)</code>, <code>STDDEV(series, len, tf?)</code>
          <br />
          - <code>RET(series, tf)</code>, <code>ATR(len, tf)</code>, <code>OBV(close, volume, tf)</code>,{' '}
          <code>VWAP(price, volume, tf)</code>
        </Typography>

        <Typography variant="subtitle2">Examples</Typography>
        <Typography variant="body2" component="div">
          <code>ATR(14, 1d) / PRICE(1d) * 100</code>
          <br />
          <code>SMA(close, 20, 1d) - SMA(close, 50, 1d)</code>
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}

function EventsV3Tab({ onOpenAlert }: { onOpenAlert: (alertId: number) => void }) {
  const [rows, setRows] = useState<AlertEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [selected, setSelected] = useState<AlertEvent | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      setRows(await listAlertEvents({ limit: 200 }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const formatIstDateTime = (value: unknown): string => {
    return formatDateTimeIst(value)
  }

  const columns: GridColDef[] = [
    { field: 'triggered_at', headerName: 'Triggered at', width: 190, valueFormatter: (v) => formatIstDateTime(v) },
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'exchange', headerName: 'Exch', width: 90, valueFormatter: (v) => (v ? String(v) : '—') },
    { field: 'alert_definition_id', headerName: 'Alert ID', width: 100 },
    { field: 'reason', headerName: 'Reason', flex: 1, minWidth: 320, valueFormatter: (v) => v ?? '—' },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 110,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Button
          size="small"
          variant="outlined"
          onClick={() => {
            setSelected(params.row as AlertEvent)
            setDetailsOpen(true)
          }}
        >
          Details
        </Button>
      ),
    },
  ]

  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Trigger history (audit trail) for trust and debugging.
      </Typography>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
        <Button variant="outlined" onClick={() => void refresh()} disabled={loading}>
          Refresh
        </Button>
      </Box>
      <Paper sx={{ height: 520, width: '100%' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          density="compact"
          loading={loading}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          initialState={{
            pagination: { paginationModel: { pageSize: 25 } },
          }}
          pageSizeOptions={[25, 50, 100]}
          localeText={{
            noRowsLabel: loading ? 'Loading...' : 'No alert events found.',
          }}
        />
      </Paper>
      <Dialog
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Event snapshot</DialogTitle>
        <DialogContent sx={{ pt: 1 }}>
          {selected ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              <Typography variant="body2" color="text.secondary">
                {selected.symbol} · {formatIstDateTime(selected.triggered_at)} · Alert{' '}
                {selected.alert_definition_id}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  variant="outlined"
                  onClick={() => {
                    onOpenAlert(selected.alert_definition_id)
                    setDetailsOpen(false)
                  }}
                >
                  Open alert
                </Button>
              </Box>
              <Paper variant="outlined" sx={{ p: 1, bgcolor: 'background.default' }}>
                <Typography
                  component="pre"
                  variant="body2"
                  sx={{ m: 0, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}
                >
                  {JSON.stringify(selected.snapshot ?? {}, null, 2)}
                </Typography>
              </Paper>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No event selected.
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailsOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

/*
Legacy indicator-rule alerts (pre v3) removed in Phase 1 cutover.
Kept temporarily for reference; guarded from compilation.

function LegacyIndicatorAlertsTab() {
  const [rows, setRows] = useState<RuleRow[]>([])
  const [templates, setTemplates] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [selectedRule, setSelectedRule] = useState<RuleRow | null>(null)
  const [corrSummary, setCorrSummary] =
    useState<HoldingsCorrelationResult | null>(null)
  const [clusterError, setClusterError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoading(true)
        setError(null)

        const [rules, templates] = await Promise.all([
          listIndicatorRules(),
          listStrategyTemplates(),
        ])

        if (!active) return

        const byId = new Map<number, Strategy>()
        templates.forEach((tpl) => {
          byId.set(tpl.id, tpl)
        })

        const mapped: RuleRow[] = rules.map((rule) => ({
          ...rule,
          strategy_name:
            rule.strategy_id != null ? byId.get(rule.strategy_id)?.name ?? null : null,
        }))
        setTemplates(templates)
        setRows(mapped)
      } catch (err) {
        if (!active) return
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load indicator alerts',
        )
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const loadClusters = async () => {
      try {
        setClusterError(null)
        const res = await fetchHoldingsCorrelation({ windowDays: 90 })
        if (!active) return
        setCorrSummary(res)
      } catch (err) {
        if (!active) return
        setClusterError(
          err instanceof Error
            ? err.message
            : 'Failed to load holdings correlation clusters.',
        )
      } finally {
        if (active) {
          // No-op; we avoid wiring cluster loading into the grid spinner so
          // that slow correlation calls do not block alert management.
        }
      }
    }

    void loadClusters()
    return () => {
      active = false
    }
  }, [])

  const strategyById = useMemo(() => {
    const m = new Map<number, Strategy>()
    templates.forEach((tpl) => m.set(tpl.id, tpl))
    return m
  }, [templates])

  const handleOpenEdit = (row: RuleRow) => {
    setSelectedRule(row)
    setEditOpen(true)
  }

  const handleCloseEdit = () => {
    setEditOpen(false)
    setSelectedRule(null)
  }

  const handleRuleUpdated = (updated: IndicatorRule) => {
    const strategyName =
      updated.strategy_id != null
        ? strategyById.get(updated.strategy_id)?.name ?? null
        : null
    setRows((prev) =>
      prev.map((r) =>
        r.id === updated.id
          ? {
              ...r,
              ...updated,
              strategy_name: strategyName,
            }
          : r,
      ),
    )
  }

  const handleDelete = async (row: RuleRow) => {
    const ok = window.confirm(
      `Delete alert for ${row.symbol ?? row.universe ?? 'rule'}?`,
    )
    if (!ok) return
    try {
      await deleteIndicatorRule(row.id)
      setRows((prev) => prev.filter((r) => r.id !== row.id))
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to delete indicator alert',
      )
    }
  }

  const formatIstDateTime = (value: unknown): string => {
    return formatDateTimeIst(value)
  }

  const columns: GridColDef[] = [
    {
      field: 'symbol',
      headerName: 'Symbol',
      width: 140,
      valueGetter: (_value, row) => row.symbol ?? row.universe ?? '-',
    },
    {
      field: 'cluster',
      headerName: 'Cluster',
      width: 100,
      valueGetter: (_value, row) => {
        const symbol = row.symbol as string | null
        if (!symbol || !corrSummary) return null
        const found = corrSummary.symbol_stats.find(
          (s) => s.symbol === symbol,
        )
        return found?.cluster ?? null
      },
    },
    {
      field: 'strategy_name',
      headerName: 'Strategy',
      width: 220,
      valueFormatter: (v) => v ?? '—',
    },
    {
      field: 'timeframe',
      headerName: 'Timeframe',
      width: 100,
    },
    {
      field: 'action_type',
      headerName: 'Action',
      width: 130,
    },
    {
      field: 'trigger_mode',
      headerName: 'Trigger',
      width: 140,
    },
    {
      field: 'enabled',
      headerName: 'Status',
      width: 120,
      renderCell: (params: GridRenderCellParams<RuleRow, boolean>) => (
        <Chip
          size="small"
          label={params.value ? 'Enabled' : 'Paused'}
          color={params.value ? 'success' : 'default'}
        />
      ),
    },
    {
      field: 'last_triggered_at',
      headerName: 'Last triggered',
      width: 190,
      valueFormatter: (v) => formatIstDateTime(v),
    },
    {
      field: 'created_at',
      headerName: 'Created at',
      width: 190,
      valueFormatter: (v) => formatIstDateTime(v),
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 200,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const row = params.row as RuleRow
        return (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => handleOpenEdit(row)}
            >
              Edit
            </Button>
            <Button
              size="small"
              color="error"
              onClick={() => void handleDelete(row)}
            >
              Delete
            </Button>
          </Box>
        )
      },
    },
  ]

  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Legacy indicator-rule alerts (pre v3).
      </Typography>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      {clusterError && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {clusterError}
        </Typography>
      )}
      <Paper sx={{ height: 520, width: '100%' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          density="compact"
          loading={loading}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          initialState={{
            pagination: { paginationModel: { pageSize: 25 } },
          }}
          pageSizeOptions={[25, 50, 100]}
          localeText={{
            noRowsLabel: loading
              ? 'Loading alerts...'
              : 'No indicator alert rules found.',
          }}
        />
      </Paper>
      <EditAlertDialog
        open={editOpen}
        rule={selectedRule}
        onClose={handleCloseEdit}
        onUpdated={handleRuleUpdated}
      />
    </Box>
  )
}
export default AlertsPage

type EditAlertDialogProps = {
  open: boolean
  rule: RuleRow | null
  onClose: () => void
  onUpdated: (rule: IndicatorRule) => void
}

	function EditAlertDialog({
	  open,
	  rule,
	  onClose,
	  onUpdated,
	}: EditAlertDialogProps) {
  const [enabled, setEnabled] = useState<boolean>(true)
  const [triggerMode, setTriggerMode] = useState<TriggerMode>('ONCE_PER_BAR')
  const [dslExpression, setDslExpression] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!rule) return
    setEnabled(rule.enabled)
    setTriggerMode(rule.trigger_mode)
    setDslExpression(rule.dsl_expression ?? '')
    setError(null)
  }, [rule])

  const handleSave = async () => {
    if (!rule) return

    const payload: IndicatorRuleUpdate = {
      enabled,
      trigger_mode: triggerMode,
	}

    if (rule.dsl_expression != null) {
      const trimmed = dslExpression.trim()
      if (!trimmed) {
        setError('DSL expression cannot be empty for this alert.')
        return
      }
      payload.dsl_expression = trimmed
    }

    setSaving(true)
    try {
      const updated = await updateIndicatorRule(rule.id, payload)
      onUpdated(updated)
      onClose()
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to update alert rule',
      )
    } finally {
      setSaving(false)
    }
  }

  const isDslRule = !!rule?.dsl_expression

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>Edit alert</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        {rule && (
          <>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              {rule.symbol ?? rule.universe ?? '—'} ({rule.timeframe})
            </Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  color="primary"
                />
              }
              label={enabled ? 'Enabled' : 'Paused'}
            />
            <Box sx={{ mt: 2, mb: 2, display: 'flex', gap: 2 }}>
              <TextField
                label="Trigger"
                select
                size="small"
                value={triggerMode}
                onChange={(e) =>
                  setTriggerMode(e.target.value as TriggerMode)
                }
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="ONCE">Only once</MenuItem>
                <MenuItem value="ONCE_PER_BAR">Once per bar</MenuItem>
                <MenuItem value="EVERY_TIME">Every time</MenuItem>
              </TextField>
            </Box>
            {isDslRule ? (
              <TextField
                label="DSL expression"
                size="small"
                value={dslExpression}
                onChange={(e) => setDslExpression(e.target.value)}
                multiline
                minRows={4}
                fullWidth
                helperText="Update the alert DSL expression; it will be validated on save."
              />
            ) : (
              <Typography variant="body2" color="text.secondary">
                This alert was created with the simple builder. You can pause or
                change its trigger mode here; edit conditions from the Holdings
                page if needed.
              </Typography>
            )}
            {error && (
              <Typography
                variant="body2"
                color="error"
                sx={{ mt: 1 }}
              >
                {error}
              </Typography>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving || !rule}
        >
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

*/
