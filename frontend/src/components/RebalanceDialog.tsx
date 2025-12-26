import AutorenewIcon from '@mui/icons-material/Autorenew'
import HistoryIcon from '@mui/icons-material/History'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'
import { useEffect, useMemo, useState } from 'react'

import rebalanceHelpText from '../../../docs/rebalance_dialog_help.md?raw'

import { MarkdownLite } from './MarkdownLite'

import {
  executeRebalance,
  fetchRebalanceSchedule,
  getRebalanceRun,
  listRebalanceRuns,
  previewRebalance,
  updateRebalanceSchedule,
  type RebalanceMethod,
  type RebalanceRotationWeighting,
  type RebalanceRiskWindow,
  type RebalancePreviewResult,
  type RebalanceRun,
  type RebalanceSchedule,
  type RebalanceScheduleConfig,
  type RebalanceScheduleFrequency,
  type RebalanceTargetKind,
} from '../services/rebalance'
import { listGroups, type Group } from '../services/groups'
import {
  listSignalStrategies,
  listSignalStrategyVersions,
  type SignalStrategy,
  type SignalStrategyVersion,
} from '../services/signalStrategies'
import { formatIst } from '../utils/datetime'

type RebalanceTradeRow = {
  id: string
  broker: string
  symbol: string
  side: 'BUY' | 'SELL'
  qty: number
  estimated_price: number
  estimated_notional: number
  target_weight: number
  live_weight: number
  drift: number
}

type RebalanceDraft = {
  brokerName: 'zerodha' | 'angelone'
  rebalanceMethod: RebalanceMethod
  budgetPct: string
  budgetAmount: string
  absBandPct: string
  relBandPct: string
  maxTrades: string
  minTradeValue: string
  rotationStrategyId: string
  rotationVersionId: string
  rotationOutput: string
  rotationParamsJson: string
  rotationUniverseGroupId: string
  rotationScreenerRunId: string
  rotationTopN: string
  rotationWeighting: RebalanceRotationWeighting
  rotationSellNotInTopN: boolean
  rotationMinPrice: string
  rotationMinAvgVolume20d: string
  rotationWhitelist: string
  rotationBlacklist: string
  rotationRequirePositiveScore: boolean
  riskWindow: RebalanceRiskWindow
  riskMinObservations: string
  riskMinWeightPct: string
  riskMaxWeightPct: string
  mode: 'MANUAL' | 'AUTO'
  executionTarget: 'LIVE' | 'PAPER'
  orderType: 'MARKET' | 'LIMIT'
  product: 'CNC' | 'MIS'
  idempotencyKey: string
}

const DEFAULT_REBALANCE: RebalanceDraft = {
  brokerName: 'zerodha',
  rebalanceMethod: 'TARGET_WEIGHT',
  budgetPct: '10',
  budgetAmount: '',
  absBandPct: '2',
  relBandPct: '15',
  maxTrades: '10',
  minTradeValue: '2000',
  rotationStrategyId: '',
  rotationVersionId: '',
  rotationOutput: '',
  rotationParamsJson: '',
  rotationUniverseGroupId: '',
  rotationScreenerRunId: '',
  rotationTopN: '10',
  rotationWeighting: 'EQUAL',
  rotationSellNotInTopN: true,
  rotationMinPrice: '',
  rotationMinAvgVolume20d: '',
  rotationWhitelist: '',
  rotationBlacklist: '',
  rotationRequirePositiveScore: true,
  riskWindow: '6M',
  riskMinObservations: '60',
  riskMinWeightPct: '0',
  riskMaxWeightPct: '100',
  mode: 'MANUAL',
  executionTarget: 'LIVE',
  orderType: 'MARKET',
  product: 'CNC',
  idempotencyKey: '',
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatIstDateTime(value: unknown): string {
  if (!value) return '—'
  const out = formatIst(value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
  return out || '—'
}

function parsePct(raw: string): number | null {
  const v = Number(raw)
  if (!Number.isFinite(v) || v < 0) return null
  return v / 100.0
}

function parseNum(raw: string): number | null {
  const v = Number(raw)
  if (!Number.isFinite(v) || v < 0) return null
  return v
}

function parseIntOrNull(raw: string): number | null {
  const v = Number(raw)
  if (!Number.isFinite(v) || v <= 0) return null
  return Math.floor(v)
}

export type RebalanceDialogProps = {
  open: boolean
  onClose: () => void
  title?: string
  targetKind: RebalanceTargetKind
  groupId?: number | null
  brokerName: 'zerodha' | 'angelone'
  brokerLocked?: boolean
  scheduleSupported?: boolean
}

export function RebalanceDialog({
  open,
  onClose,
  title,
  targetKind,
  groupId,
  brokerName,
  brokerLocked,
  scheduleSupported,
}: RebalanceDialogProps) {
  const historyEnabled = targetKind === 'GROUP' && groupId != null
  const advancedMethodsSupported = historyEnabled && !!scheduleSupported
  const [tab, setTab] = useState<'preview' | 'history' | 'schedule'>('preview')
  const [helpOpen, setHelpOpen] = useState(false)
  const [helpTab, setHelpTab] = useState<string>('Overview')
  const [draft, setDraft] = useState<RebalanceDraft>(() => ({
    ...DEFAULT_REBALANCE,
    brokerName,
  }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [previewResults, setPreviewResults] = useState<RebalancePreviewResult[] | null>(
    null,
  )
  const [runs, setRuns] = useState<RebalanceRun[]>([])
  const [selectedRun, setSelectedRun] = useState<RebalanceRun | null>(null)
  const [schedule, setSchedule] = useState<RebalanceSchedule | null>(null)
  const [scheduleDraft, setScheduleDraft] =
    useState<RebalanceScheduleConfig | null>(null)
  const [scheduleEnabled, setScheduleEnabled] = useState(true)
  const [groups, setGroups] = useState<Group[]>([])
  const [signalStrategies, setSignalStrategies] = useState<SignalStrategy[]>([])
  const [signalVersions, setSignalVersions] = useState<SignalStrategyVersion[]>([])

  useEffect(() => {
    if (!open) return
    setTab('preview')
    setDraft({ ...DEFAULT_REBALANCE, brokerName })
    setError(null)
    setPreviewResults(null)
    setSelectedRun(null)
    setRuns([])
    setSchedule(null)
    setScheduleDraft(null)
    setScheduleEnabled(true)
    setGroups([])
    setSignalStrategies([])
    setSignalVersions([])
    setHelpTab('Overview')

    if (historyEnabled) {
      void (async () => {
        try {
          const rows = await listRebalanceRuns({
            group_id: groupId as number,
            broker_name: null,
          })
          setRuns(rows)
        } catch {
          // best-effort
        }
      })()
    }

    if (historyEnabled && scheduleSupported) {
      void (async () => {
        try {
          const s = await fetchRebalanceSchedule(groupId as number)
          setSchedule(s)
          setScheduleDraft(s.config)
          setScheduleEnabled(!!s.enabled)
        } catch {
          // best-effort
        }
      })()
    }

    if (advancedMethodsSupported) {
      void (async () => {
        try {
          const [gs, ss] = await Promise.all([
            listGroups(),
            listSignalStrategies({ includeLatest: true, includeUsage: false }),
          ])
          setGroups(gs)
          setSignalStrategies(ss)
        } catch {
          // best-effort
        }
      })()
    }
  }, [open, brokerName, historyEnabled, groupId, scheduleSupported, advancedMethodsSupported])

  const helpSections = useMemo(() => {
    const raw = rebalanceHelpText || ''
    const lines = raw.split(/\r?\n/)
    const sections: Array<{ title: string; start: number; end: number }> = []
    let currentTitle = 'Overview'
    let start = 0
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      if (line.startsWith('## ')) {
        sections.push({ title: currentTitle, start, end: i })
        currentTitle = line.slice(3).trim() || 'Overview'
        start = i
      }
    }
    sections.push({ title: currentTitle, start, end: lines.length })
    const out: Record<string, string> = {}
    for (const s of sections) {
      const text = lines.slice(s.start, s.end).join('\n').trim()
      if (!text) continue
      out[s.title] = text
    }
    if (!out.Overview) out.Overview = raw.trim()
    return out
  }, [])

  const helpTabs = useMemo(() => {
    const preferred = [
      'Overview',
      'Target weights',
      'Signal rotation',
      'Risk parity',
      'Columns & calculations',
      'Scheduling & history',
      'FAQ',
    ]
    return preferred.filter((k) => helpSections[k])
  }, [helpSections])

  useEffect(() => {
    if (!open || !advancedMethodsSupported) return
    const strategyId = Number(draft.rotationStrategyId)
    if (!Number.isFinite(strategyId) || strategyId <= 0) {
      setSignalVersions([])
      return
    }
    void (async () => {
      try {
        const versions = await listSignalStrategyVersions(strategyId)
        setSignalVersions(versions)
        if (!versions.length) return
        const latest = versions.reduce(
          (best, v) => (v.version > best.version ? v : best),
          versions[0],
        )
        setDraft((prev) => {
          if (prev.rotationVersionId && prev.rotationOutput) return prev
          return {
            ...prev,
            rotationVersionId: prev.rotationVersionId || String(latest.id),
            rotationOutput:
              prev.rotationOutput ||
              (latest.outputs.find((o) => o.kind === 'OVERLAY')?.name ?? ''),
          }
        })
      } catch {
        setSignalVersions([])
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, advancedMethodsSupported, draft.rotationStrategyId])

  const selectedVersion = useMemo(() => {
    const vid = Number(draft.rotationVersionId)
    if (!Number.isFinite(vid) || vid <= 0) return null
    return signalVersions.find((v) => v.id === vid) ?? null
  }, [draft.rotationVersionId, signalVersions])

  const overlayOutputs = useMemo(() => {
    return (selectedVersion?.outputs ?? []).filter((o) => o.kind === 'OVERLAY')
  }, [selectedVersion])

  const saveSchedule = async () => {
    if (!historyEnabled || !scheduleSupported || !groupId || !scheduleDraft) return
    try {
      setBusy(true)
      setError(null)
      const updated = await updateRebalanceSchedule(groupId, {
        enabled: scheduleEnabled,
        config: scheduleDraft,
      })
      setSchedule(updated)
      setScheduleDraft(updated.config)
      setScheduleEnabled(!!updated.enabled)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update schedule')
    } finally {
      setBusy(false)
    }
  }

  const tradeRows = useMemo((): RebalanceTradeRow[] => {
    const results = previewResults ?? []
    const rows: RebalanceTradeRow[] = []
    for (const r of results) {
      for (const t of r.trades ?? []) {
        rows.push({
          id: `${r.broker_name}:${t.symbol}:${t.side}`,
          broker: r.broker_name,
          symbol: t.symbol,
          side: t.side,
          qty: t.qty,
          estimated_price: t.estimated_price,
          estimated_notional: t.estimated_notional,
          target_weight: t.target_weight,
          live_weight: t.live_weight,
          drift: t.drift,
        })
      }
    }
    return rows
  }, [previewResults])

  const tradeColumns: GridColDef<RebalanceTradeRow>[] = [
    { field: 'broker', headerName: 'Broker', width: 110 },
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'side', headerName: 'Side', width: 90 },
    { field: 'qty', headerName: 'Qty', type: 'number', width: 90 },
    {
      field: 'estimated_price',
      headerName: 'Est. price',
      width: 110,
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
    },
    {
      field: 'estimated_notional',
      headerName: 'Est. notional',
      width: 140,
      valueFormatter: (v) => (v != null ? Number(v).toFixed(0) : '—'),
    },
    {
      field: 'target_weight',
      headerName: 'Target',
      width: 110,
      valueFormatter: (v) => formatPercent(v as number | null),
    },
    {
      field: 'live_weight',
      headerName: 'Live',
      width: 110,
      valueFormatter: (v) => formatPercent(v as number | null),
    },
    {
      field: 'drift',
      headerName: 'Drift',
      width: 110,
      valueFormatter: (v) => formatPercent(v as number | null),
    },
  ]

  const runsColumns: GridColDef<RebalanceRun>[] = [
    { field: 'id', headerName: 'Run id', width: 90 },
    { field: 'broker_name', headerName: 'Broker', width: 110 },
    { field: 'status', headerName: 'Status', width: 110 },
    {
      field: 'created_at',
      headerName: 'Created',
      width: 190,
      valueFormatter: (v) => formatIstDateTime(v),
    },
    {
      field: 'executed_at',
      headerName: 'Executed',
      width: 190,
      valueFormatter: (v) => formatIstDateTime(v),
    },
    {
      field: 'orders_count',
      headerName: '#Orders',
      width: 110,
      valueGetter: (_v, row) => row.orders?.length ?? 0,
    },
    { field: 'error_message', headerName: 'Error', flex: 1, minWidth: 200 },
  ]

  const runOrderColumns: GridColDef<RebalanceRun['orders'][number]>[] = [
    { field: 'order_id', headerName: 'Order id', width: 95 },
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'side', headerName: 'Side', width: 90 },
    { field: 'qty', headerName: 'Qty', type: 'number', width: 90 },
    {
      field: 'estimated_notional',
      headerName: 'Est. notional',
      width: 140,
      valueFormatter: (v) => (v != null ? Number(v).toFixed(0) : '—'),
    },
    { field: 'status', headerName: 'Status', width: 140 },
  ]

  const runPreview = async () => {
    try {
      setBusy(true)
      setError(null)
      const budgetAmount = draft.budgetAmount.trim() ? parseNum(draft.budgetAmount.trim()) : null
      const budgetPct = draft.budgetPct.trim() ? parsePct(draft.budgetPct.trim()) : null
      const absBand = draft.absBandPct.trim() ? parsePct(draft.absBandPct.trim()) : null
      const relBand = draft.relBandPct.trim() ? parsePct(draft.relBandPct.trim()) : null
      const maxTradesRaw = Number(draft.maxTrades)
      const maxTrades =
        Number.isFinite(maxTradesRaw) && maxTradesRaw >= 0 ? Math.floor(maxTradesRaw) : null
      const minTradeValue = draft.minTradeValue.trim() ? parseNum(draft.minTradeValue.trim()) : null

      let rotationPayload: any = null
      if (advancedMethodsSupported && draft.rebalanceMethod === 'SIGNAL_ROTATION') {
        const versionId = parseIntOrNull(draft.rotationVersionId.trim())
        if (!versionId) throw new Error('Rotation: select a strategy version')
        const outputName = draft.rotationOutput.trim()
        if (!outputName) throw new Error('Rotation: select an output (OVERLAY)')
        const topN = parseIntOrNull(draft.rotationTopN.trim())
        if (!topN) throw new Error('Rotation: enter a valid Top N')
        const universeGroupId = draft.rotationUniverseGroupId.trim()
          ? parseIntOrNull(draft.rotationUniverseGroupId.trim())
          : null
        const screenerRunId = draft.rotationScreenerRunId.trim()
          ? parseIntOrNull(draft.rotationScreenerRunId.trim())
          : null
        if (universeGroupId && screenerRunId)
          throw new Error('Rotation: choose either Universe group or Screener run id (not both)')

        let paramsObj: Record<string, unknown> = {}
        if (draft.rotationParamsJson.trim()) {
          try {
            const parsed = JSON.parse(draft.rotationParamsJson.trim()) as unknown
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
              paramsObj = parsed as Record<string, unknown>
            } else {
              throw new Error('Signal params must be a JSON object')
            }
          } catch (e) {
            throw new Error(
              `Rotation: invalid Signal params JSON${
                e instanceof Error && e.message ? `: ${e.message}` : ''
              }`,
            )
          }
        }

        const minPrice = draft.rotationMinPrice.trim() ? parseNum(draft.rotationMinPrice.trim()) : null
        const minAvgVol = draft.rotationMinAvgVolume20d.trim()
          ? parseNum(draft.rotationMinAvgVolume20d.trim())
          : null
        const whitelist = draft.rotationWhitelist
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        const blacklist = draft.rotationBlacklist
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)

        rotationPayload = {
          signal_strategy_version_id: versionId,
          signal_output: outputName,
          signal_params: paramsObj,
          universe_group_id: universeGroupId,
          screener_run_id: screenerRunId,
          top_n: topN,
          weighting: draft.rotationWeighting,
          sell_not_in_top_n: !!draft.rotationSellNotInTopN,
          min_price: minPrice,
          min_avg_volume_20d: minAvgVol,
          symbol_whitelist: whitelist,
          symbol_blacklist: blacklist,
          require_positive_score: !!draft.rotationRequirePositiveScore,
        }
      }

      let riskPayload: any = null
      if (advancedMethodsSupported && draft.rebalanceMethod === 'RISK_PARITY') {
        const minObs = parseIntOrNull(draft.riskMinObservations.trim()) ?? 60
        const minW = draft.riskMinWeightPct.trim() ? parsePct(draft.riskMinWeightPct.trim()) : 0
        const maxW = draft.riskMaxWeightPct.trim() ? parsePct(draft.riskMaxWeightPct.trim()) : 1
        if (minW == null || maxW == null) throw new Error('Risk: invalid min/max weight')
        riskPayload = {
          window: draft.riskWindow,
          timeframe: '1d',
          min_observations: minObs,
          min_weight: minW,
          max_weight: maxW,
          max_iter: 2000,
          tol: 1e-8,
        }
      }

      const results = await previewRebalance({
        target_kind: targetKind,
        group_id: targetKind === 'GROUP' ? (groupId ?? null) : null,
        broker_name: draft.brokerName,
        rebalance_method: draft.rebalanceMethod,
        rotation: rotationPayload,
        risk: riskPayload,
        budget_pct: budgetPct,
        budget_amount: budgetAmount,
        drift_band_abs_pct: absBand,
        drift_band_rel_pct: relBand,
        max_trades: maxTrades,
        min_trade_value: minTradeValue,
      })
      setPreviewResults(results)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to preview rebalance')
    } finally {
      setBusy(false)
    }
  }

  const runExecute = async () => {
    try {
      setBusy(true)
      setError(null)
      const budgetAmount = draft.budgetAmount.trim() ? parseNum(draft.budgetAmount.trim()) : null
      const budgetPct = draft.budgetPct.trim() ? parsePct(draft.budgetPct.trim()) : null
      const absBand = draft.absBandPct.trim() ? parsePct(draft.absBandPct.trim()) : null
      const relBand = draft.relBandPct.trim() ? parsePct(draft.relBandPct.trim()) : null
      const maxTradesRaw = Number(draft.maxTrades)
      const maxTrades =
        Number.isFinite(maxTradesRaw) && maxTradesRaw >= 0 ? Math.floor(maxTradesRaw) : null
      const minTradeValue = draft.minTradeValue.trim() ? parseNum(draft.minTradeValue.trim()) : null
      const idem =
        historyEnabled && draft.idempotencyKey.trim() ? draft.idempotencyKey.trim() : null

      let rotationPayload: any = null
      if (advancedMethodsSupported && draft.rebalanceMethod === 'SIGNAL_ROTATION') {
        const versionId = parseIntOrNull(draft.rotationVersionId.trim())
        if (!versionId) throw new Error('Rotation: select a strategy version')
        const outputName = draft.rotationOutput.trim()
        if (!outputName) throw new Error('Rotation: select an output (OVERLAY)')
        const topN = parseIntOrNull(draft.rotationTopN.trim())
        if (!topN) throw new Error('Rotation: enter a valid Top N')
        const universeGroupId = draft.rotationUniverseGroupId.trim()
          ? parseIntOrNull(draft.rotationUniverseGroupId.trim())
          : null
        const screenerRunId = draft.rotationScreenerRunId.trim()
          ? parseIntOrNull(draft.rotationScreenerRunId.trim())
          : null
        if (universeGroupId && screenerRunId)
          throw new Error('Rotation: choose either Universe group or Screener run id (not both)')

        let paramsObj: Record<string, unknown> = {}
        if (draft.rotationParamsJson.trim()) {
          try {
            const parsed = JSON.parse(draft.rotationParamsJson.trim()) as unknown
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
              paramsObj = parsed as Record<string, unknown>
            } else {
              throw new Error('Signal params must be a JSON object')
            }
          } catch (e) {
            throw new Error(
              `Rotation: invalid Signal params JSON${
                e instanceof Error && e.message ? `: ${e.message}` : ''
              }`,
            )
          }
        }

        const minPrice = draft.rotationMinPrice.trim() ? parseNum(draft.rotationMinPrice.trim()) : null
        const minAvgVol = draft.rotationMinAvgVolume20d.trim()
          ? parseNum(draft.rotationMinAvgVolume20d.trim())
          : null
        const whitelist = draft.rotationWhitelist
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        const blacklist = draft.rotationBlacklist
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)

        rotationPayload = {
          signal_strategy_version_id: versionId,
          signal_output: outputName,
          signal_params: paramsObj,
          universe_group_id: universeGroupId,
          screener_run_id: screenerRunId,
          top_n: topN,
          weighting: draft.rotationWeighting,
          sell_not_in_top_n: !!draft.rotationSellNotInTopN,
          min_price: minPrice,
          min_avg_volume_20d: minAvgVol,
          symbol_whitelist: whitelist,
          symbol_blacklist: blacklist,
          require_positive_score: !!draft.rotationRequirePositiveScore,
        }
      }

      let riskPayload: any = null
      if (advancedMethodsSupported && draft.rebalanceMethod === 'RISK_PARITY') {
        const minObs = parseIntOrNull(draft.riskMinObservations.trim()) ?? 60
        const minW = draft.riskMinWeightPct.trim() ? parsePct(draft.riskMinWeightPct.trim()) : 0
        const maxW = draft.riskMaxWeightPct.trim() ? parsePct(draft.riskMaxWeightPct.trim()) : 1
        if (minW == null || maxW == null) throw new Error('Risk: invalid min/max weight')
        riskPayload = {
          window: draft.riskWindow,
          timeframe: '1d',
          min_observations: minObs,
          min_weight: minW,
          max_weight: maxW,
          max_iter: 2000,
          tol: 1e-8,
        }
      }

      const results = await executeRebalance({
        target_kind: targetKind,
        group_id: targetKind === 'GROUP' ? (groupId ?? null) : null,
        broker_name: draft.brokerName,
        rebalance_method: draft.rebalanceMethod,
        rotation: rotationPayload,
        risk: riskPayload,
        budget_pct: budgetPct,
        budget_amount: budgetAmount,
        drift_band_abs_pct: absBand,
        drift_band_rel_pct: relBand,
        max_trades: maxTrades,
        min_trade_value: minTradeValue,
        mode: draft.mode,
        execution_target: draft.executionTarget,
        order_type: draft.orderType,
        product: draft.product,
        idempotency_key: idem,
      })

      const firstRun = results[0]?.run ?? null
      if (firstRun) {
        setSelectedRun(firstRun)
      }
      if (historyEnabled) {
        const rows = await listRebalanceRuns({ group_id: groupId as number, broker_name: null })
        setRuns(rows)
        setTab('history')
      }

      if (historyEnabled && scheduleSupported) {
        try {
          const s = await fetchRebalanceSchedule(groupId as number)
          setSchedule(s)
          setScheduleDraft(s.config)
          setScheduleEnabled(!!s.enabled)
        } catch {
          // best-effort
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute rebalance')
    } finally {
      setBusy(false)
    }
  }

  const scheduleNextLabel = schedule?.next_run_at
    ? `Next: ${formatIstDateTime(schedule.next_run_at)}`
    : 'Next: —'
  const scheduleLastLabel = schedule?.last_run_at
    ? `Last: ${formatIstDateTime(schedule.last_run_at)}`
    : 'Last: —'

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ flexGrow: 1 }}>{title || 'Rebalance'}</Box>
          <Tooltip title="Help">
            <IconButton size="small" onClick={() => setHelpOpen(true)}>
              <HelpOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </DialogTitle>
      <DialogContent>
        <Tabs
          value={tab}
          onChange={(_e, v) => setTab(v as 'preview' | 'history' | 'schedule')}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Preview" value="preview" icon={<AutorenewIcon />} iconPosition="start" />
          {historyEnabled && (
            <Tab label="History" value="history" icon={<HistoryIcon />} iconPosition="start" />
          )}
          {historyEnabled && scheduleSupported && (
            <Tab label="Schedule" value="schedule" icon={<HistoryIcon />} iconPosition="start" />
          )}
        </Tabs>

        {historyEnabled && scheduleSupported && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            {scheduleLastLabel} • {scheduleNextLabel}
          </Typography>
        )}

        {tab === 'preview' && (
          <Stack spacing={2} sx={{ mt: 2 }}>
            {advancedMethodsSupported && (
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <FormControl sx={{ width: { xs: '100%', md: 240 } }}>
                  <InputLabel id="rebalance-method-label">Rebalance method</InputLabel>
                  <Select
                    labelId="rebalance-method-label"
                    label="Rebalance method"
                    value={draft.rebalanceMethod}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        rebalanceMethod: e.target.value as RebalanceMethod,
                      }))
                    }
                  >
                    <MenuItem value="TARGET_WEIGHT">Target weights</MenuItem>
                    <MenuItem value="SIGNAL_ROTATION">Signal-driven rotation</MenuItem>
                    <MenuItem value="RISK_PARITY">Risk parity (equal risk)</MenuItem>
                  </Select>
                </FormControl>
              </Stack>
            )}

            {advancedMethodsSupported && draft.rebalanceMethod === 'SIGNAL_ROTATION' && (
              <Stack spacing={2}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <FormControl sx={{ width: { xs: '100%', md: 260 } }}>
                    <InputLabel id="rot-strategy-label">Strategy</InputLabel>
                    <Select
                      labelId="rot-strategy-label"
                      label="Strategy"
                      value={draft.rotationStrategyId}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          rotationStrategyId: String(e.target.value),
                          rotationVersionId: '',
                          rotationOutput: '',
                        }))
                      }
                    >
                      {signalStrategies.map((s) => (
                        <MenuItem key={s.id} value={String(s.id)}>
                          {s.name} (#{s.id})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <FormControl sx={{ width: { xs: '100%', md: 220 } }}>
                    <InputLabel id="rot-version-label">Version</InputLabel>
                    <Select
                      labelId="rot-version-label"
                      label="Version"
                      value={draft.rotationVersionId}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          rotationVersionId: String(e.target.value),
                          rotationOutput: '',
                        }))
                      }
                    >
                      {signalVersions.map((v) => (
                        <MenuItem key={v.id} value={String(v.id)}>
                          v{v.version} (#{v.id})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <FormControl sx={{ width: { xs: '100%', md: 220 } }}>
                    <InputLabel id="rot-output-label">Output</InputLabel>
                    <Select
                      labelId="rot-output-label"
                      label="Output"
                      value={draft.rotationOutput}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          rotationOutput: String(e.target.value),
                        }))
                      }
                    >
                      {overlayOutputs.map((o) => (
                        <MenuItem key={o.name} value={o.name}>
                          {o.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <TextField
                    label="Top N"
                    value={draft.rotationTopN}
                    onChange={(e) => setDraft((prev) => ({ ...prev, rotationTopN: e.target.value }))}
                    sx={{ width: { xs: '100%', md: 140 } }}
                  />
                  <FormControl sx={{ width: { xs: '100%', md: 200 } }}>
                    <InputLabel id="rot-weighting-label">Weighting</InputLabel>
                    <Select
                      labelId="rot-weighting-label"
                      label="Weighting"
                      value={draft.rotationWeighting}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          rotationWeighting: e.target.value as RebalanceRotationWeighting,
                        }))
                      }
                    >
                      <MenuItem value="EQUAL">Equal</MenuItem>
                      <MenuItem value="SCORE">Score-proportional</MenuItem>
                      <MenuItem value="RANK">Rank-based</MenuItem>
                    </Select>
                  </FormControl>

                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={draft.rotationSellNotInTopN}
                        onChange={(e) =>
                          setDraft((prev) => ({
                            ...prev,
                            rotationSellNotInTopN: e.target.checked,
                          }))
                        }
                      />
                    }
                    label="Sell positions not in Top N"
                  />
                </Stack>

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <FormControl sx={{ width: { xs: '100%', md: 320 } }}>
                    <InputLabel id="rot-universe-group-label">Universe group (optional)</InputLabel>
                    <Select
                      labelId="rot-universe-group-label"
                      label="Universe group (optional)"
                      value={draft.rotationUniverseGroupId}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          rotationUniverseGroupId: String(e.target.value),
                        }))
                      }
                    >
                      <MenuItem value="">(Use this portfolio group)</MenuItem>
                      {groups.map((g) => (
                        <MenuItem key={g.id} value={String(g.id)}>
                          {g.name} ({g.kind}) (#{g.id})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <TextField
                    label="Screener run id (optional)"
                    value={draft.rotationScreenerRunId}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, rotationScreenerRunId: e.target.value }))
                    }
                    helperText="Alternative to Universe group."
                    sx={{ width: { xs: '100%', md: 220 } }}
                  />
                </Stack>

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <TextField
                    label="Min price (optional)"
                    value={draft.rotationMinPrice}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, rotationMinPrice: e.target.value }))
                    }
                    sx={{ width: { xs: '100%', md: 200 } }}
                  />
                  <TextField
                    label="Min avg volume 20d (optional)"
                    value={draft.rotationMinAvgVolume20d}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, rotationMinAvgVolume20d: e.target.value }))
                    }
                    sx={{ width: { xs: '100%', md: 240 } }}
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={draft.rotationRequirePositiveScore}
                        onChange={(e) =>
                          setDraft((prev) => ({
                            ...prev,
                            rotationRequirePositiveScore: e.target.checked,
                          }))
                        }
                      />
                    }
                    label="Require positive score"
                  />
                </Stack>

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <TextField
                    label="Whitelist (comma-separated)"
                    value={draft.rotationWhitelist}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, rotationWhitelist: e.target.value }))
                    }
                    sx={{ width: { xs: '100%', md: 360 } }}
                  />
                  <TextField
                    label="Blacklist (comma-separated)"
                    value={draft.rotationBlacklist}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, rotationBlacklist: e.target.value }))
                    }
                    sx={{ width: { xs: '100%', md: 360 } }}
                  />
                </Stack>

                <TextField
                  label="Signal params (JSON, optional)"
                  value={draft.rotationParamsJson}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, rotationParamsJson: e.target.value }))
                  }
                  helperText={
                    selectedVersion?.inputs?.length
                      ? `Inputs: ${selectedVersion.inputs.map((i) => i.name).join(', ')}`
                      : 'Overrides strategy input defaults.'
                  }
                  multiline
                  minRows={2}
                />
              </Stack>
            )}

            {advancedMethodsSupported && draft.rebalanceMethod === 'RISK_PARITY' && (
              <Stack spacing={2}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <FormControl sx={{ width: { xs: '100%', md: 220 } }}>
                    <InputLabel id="risk-window-label">Window</InputLabel>
                    <Select
                      labelId="risk-window-label"
                      label="Window"
                      value={draft.riskWindow}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          riskWindow: e.target.value as RebalanceRiskWindow,
                        }))
                      }
                    >
                      <MenuItem value="6M">6M</MenuItem>
                      <MenuItem value="1Y">1Y</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    label="Min observations"
                    value={draft.riskMinObservations}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        riskMinObservations: e.target.value,
                      }))
                    }
                    helperText="Aligned daily candles across all symbols."
                    sx={{ width: { xs: '100%', md: 220 } }}
                  />
                  <TextField
                    label="Min weight (%)"
                    value={draft.riskMinWeightPct}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        riskMinWeightPct: e.target.value,
                      }))
                    }
                    sx={{ width: { xs: '100%', md: 180 } }}
                  />
                  <TextField
                    label="Max weight (%)"
                    value={draft.riskMaxWeightPct}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        riskMaxWeightPct: e.target.value,
                      }))
                    }
                    sx={{ width: { xs: '100%', md: 180 } }}
                  />
                </Stack>
              </Stack>
            )}

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControl sx={{ width: { xs: '100%', md: 180 } }}>
                <InputLabel id="rebalance-broker-label">Broker</InputLabel>
                <Select
                  labelId="rebalance-broker-label"
                  label="Broker"
                  value={draft.brokerName}
                  disabled={!!brokerLocked}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      brokerName: e.target.value as RebalanceDraft['brokerName'],
                    }))
                  }
                >
                  <MenuItem value="zerodha">Zerodha</MenuItem>
                  <MenuItem value="angelone">AngelOne</MenuItem>
                </Select>
              </FormControl>

              <TextField
                label="Budget (%)"
                value={draft.budgetPct}
                onChange={(e) => setDraft((prev) => ({ ...prev, budgetPct: e.target.value }))}
                sx={{ width: { xs: '100%', md: 140 } }}
              />
              <TextField
                label="Budget amount (INR)"
                value={draft.budgetAmount}
                onChange={(e) => setDraft((prev) => ({ ...prev, budgetAmount: e.target.value }))}
                helperText="Overrides budget % when set."
                sx={{ width: { xs: '100%', md: 200 } }}
              />
              <TextField
                label="Abs band (%)"
                value={draft.absBandPct}
                onChange={(e) => setDraft((prev) => ({ ...prev, absBandPct: e.target.value }))}
                sx={{ width: { xs: '100%', md: 140 } }}
              />
              <TextField
                label="Rel band (%)"
                value={draft.relBandPct}
                onChange={(e) => setDraft((prev) => ({ ...prev, relBandPct: e.target.value }))}
                sx={{ width: { xs: '100%', md: 140 } }}
              />
            </Stack>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label="Max trades"
                value={draft.maxTrades}
                onChange={(e) => setDraft((prev) => ({ ...prev, maxTrades: e.target.value }))}
                sx={{ width: { xs: '100%', md: 140 } }}
              />
              <TextField
                label="Min trade value (INR)"
                value={draft.minTradeValue}
                onChange={(e) => setDraft((prev) => ({ ...prev, minTradeValue: e.target.value }))}
                sx={{ width: { xs: '100%', md: 200 } }}
              />
              <FormControl sx={{ width: { xs: '100%', md: 160 } }}>
                <InputLabel id="rebalance-mode-label">Mode</InputLabel>
                <Select
                  labelId="rebalance-mode-label"
                  label="Mode"
                  value={draft.mode}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, mode: e.target.value as RebalanceDraft['mode'] }))
                  }
                >
                  <MenuItem value="MANUAL">MANUAL</MenuItem>
                  <MenuItem value="AUTO">AUTO</MenuItem>
                </Select>
              </FormControl>
              <FormControl sx={{ width: { xs: '100%', md: 170 } }}>
                <InputLabel id="rebalance-target-label">Target</InputLabel>
                <Select
                  labelId="rebalance-target-label"
                  label="Target"
                  value={draft.executionTarget}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      executionTarget: e.target.value as RebalanceDraft['executionTarget'],
                    }))
                  }
                >
                  <MenuItem value="LIVE">LIVE</MenuItem>
                  <MenuItem value="PAPER">PAPER</MenuItem>
                </Select>
              </FormControl>
              <FormControl sx={{ width: { xs: '100%', md: 170 } }}>
                <InputLabel id="rebalance-order-type-label">Order type</InputLabel>
                <Select
                  labelId="rebalance-order-type-label"
                  label="Order type"
                  value={draft.orderType}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      orderType: e.target.value as RebalanceDraft['orderType'],
                    }))
                  }
                >
                  <MenuItem value="MARKET">MARKET</MenuItem>
                  <MenuItem value="LIMIT">LIMIT</MenuItem>
                </Select>
              </FormControl>
              <FormControl sx={{ width: { xs: '100%', md: 140 } }}>
                <InputLabel id="rebalance-product-label">Product</InputLabel>
                <Select
                  labelId="rebalance-product-label"
                  label="Product"
                  value={draft.product}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      product: e.target.value as RebalanceDraft['product'],
                    }))
                  }
                >
                  <MenuItem value="CNC">CNC</MenuItem>
                  <MenuItem value="MIS">MIS</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            {historyEnabled && (
              <TextField
                label="Idempotency key (optional)"
                value={draft.idempotencyKey}
                onChange={(e) => setDraft((prev) => ({ ...prev, idempotencyKey: e.target.value }))}
                helperText="Prevents accidental duplicates on retries."
              />
            )}

            <Stack direction="row" spacing={1} alignItems="center">
              <Button variant="outlined" disabled={busy} onClick={() => void runPreview()}>
                Preview
              </Button>
              <Button variant="contained" disabled={busy} onClick={() => void runExecute()}>
                {draft.mode === 'AUTO' ? 'Execute now' : 'Create queued orders'}
              </Button>
              {error && <Typography color="error">{error}</Typography>}
            </Stack>

            {previewResults?.length ? (
              <Stack spacing={1}>
                {previewResults.map((r) => (
                  <Paper key={r.broker_name} variant="outlined" sx={{ p: 1 }}>
                    <Typography variant="subtitle2">
                      {r.broker_name.toUpperCase()} — trades: {r.summary.trades_count}, budget used:{' '}
                      {r.summary.budget_used.toFixed(0)} ({r.summary.budget_used_pct.toFixed(1)}%), turnover:{' '}
                      {r.summary.turnover_pct.toFixed(1)}%
                    </Typography>
                    {r.warnings?.length ? (
                      <Typography variant="caption" color="text.secondary">
                        Warnings: {r.warnings.join(' | ')}
                      </Typography>
                    ) : null}
                  </Paper>
                ))}
                <Box sx={{ height: 360 }}>
                  <DataGrid
                    rows={tradeRows}
                    columns={tradeColumns}
                    getRowId={(r) => r.id}
                    disableRowSelectionOnClick
                    pageSizeOptions={[10, 25, 50]}
                    initialState={{
                      pagination: { paginationModel: { pageSize: 10, page: 0 } },
                    }}
                  />
                </Box>
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Preview to see proposed trades.
              </Typography>
            )}
          </Stack>
        )}

        {tab === 'history' && historyEnabled && (
          <Stack spacing={2} sx={{ mt: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="outlined"
                startIcon={<HistoryIcon />}
                disabled={busy}
                onClick={() => {
                  void (async () => {
                    try {
                      setBusy(true)
                      const rows = await listRebalanceRuns({ group_id: groupId as number, broker_name: null })
                      setRuns(rows)
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Failed to load history')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }}
              >
                Refresh
              </Button>
              {error && <Typography color="error">{error}</Typography>}
            </Stack>

            <Box sx={{ height: 320 }}>
              <DataGrid
                rows={runs}
                columns={runsColumns}
                getRowId={(r) => r.id}
                disableRowSelectionOnClick
                onRowClick={(params) => {
                  const id = Number(params.row.id)
                  if (!Number.isFinite(id)) return
                  void (async () => {
                    try {
                      setBusy(true)
                      const run = await getRebalanceRun(id)
                      setSelectedRun(run)
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Failed to load run')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }}
                pageSizeOptions={[10, 25, 50]}
                initialState={{
                  pagination: { paginationModel: { pageSize: 10, page: 0 } },
                }}
              />
            </Box>

            {selectedRun && (
              <>
                <Typography variant="subtitle2">
                  Run {selectedRun.id} ({selectedRun.broker_name}) — {selectedRun.status}
                </Typography>
                <Box sx={{ height: 260 }}>
                  <DataGrid
                    rows={selectedRun.orders ?? []}
                    columns={runOrderColumns}
                    getRowId={(r) => r.id}
                    disableRowSelectionOnClick
                    pageSizeOptions={[10, 25, 50]}
                    initialState={{
                      pagination: { paginationModel: { pageSize: 10, page: 0 } },
                    }}
                  />
                </Box>
              </>
            )}
          </Stack>
        )}

        {tab === 'schedule' && historyEnabled && scheduleSupported && (
          <Stack spacing={2} sx={{ mt: 2 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center">
              <FormControl sx={{ width: { xs: '100%', md: 180 } }}>
                <InputLabel id="sched-enabled-label">Enabled</InputLabel>
                <Select
                  labelId="sched-enabled-label"
                  label="Enabled"
                  value={scheduleEnabled ? 'yes' : 'no'}
                  onChange={(e) => setScheduleEnabled(String(e.target.value) === 'yes')}
                >
                  <MenuItem value="yes">Yes</MenuItem>
                  <MenuItem value="no">No</MenuItem>
                </Select>
              </FormControl>

              <FormControl sx={{ width: { xs: '100%', md: 200 } }}>
                <InputLabel id="sched-frequency-label">Frequency</InputLabel>
                <Select
                  labelId="sched-frequency-label"
                  label="Frequency"
                  value={scheduleDraft?.frequency ?? 'MONTHLY'}
                  onChange={(e) => {
                    const freq = String(e.target.value) as RebalanceScheduleFrequency
                    setScheduleDraft((prev) =>
                      prev
                        ? {
                            ...prev,
                            frequency: freq,
                          }
                        : null,
                    )
                  }}
                >
                  <MenuItem value="WEEKLY">Weekly</MenuItem>
                  <MenuItem value="MONTHLY">Monthly</MenuItem>
                  <MenuItem value="QUARTERLY">Quarterly</MenuItem>
                  <MenuItem value="CUSTOM_DAYS">Every N days</MenuItem>
                </Select>
              </FormControl>

              <TextField
                label="Time (HH:MM)"
                value={scheduleDraft?.time_local ?? '15:10'}
                onChange={(e) =>
                  setScheduleDraft((prev) =>
                    prev ? { ...prev, time_local: e.target.value } : null,
                  )
                }
                sx={{ width: { xs: '100%', md: 160 } }}
              />

              <FormControl sx={{ width: { xs: '100%', md: 200 } }}>
                <InputLabel id="sched-tz-label">Timezone</InputLabel>
                <Select
                  labelId="sched-tz-label"
                  label="Timezone"
                  value={scheduleDraft?.timezone ?? 'Asia/Kolkata'}
                  onChange={(e) =>
                    setScheduleDraft((prev) =>
                      prev ? { ...prev, timezone: String(e.target.value) } : null,
                    )
                  }
                >
                  <MenuItem value="Asia/Kolkata">Asia/Kolkata</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            {scheduleDraft?.frequency === 'WEEKLY' && (
              <FormControl sx={{ width: { xs: '100%', md: 260 } }}>
                <InputLabel id="sched-weekday-label">Day of week</InputLabel>
                <Select
                  labelId="sched-weekday-label"
                  label="Day of week"
                  value={String(scheduleDraft.weekday ?? 4)}
                  onChange={(e) =>
                    setScheduleDraft((prev) =>
                      prev
                        ? { ...prev, weekday: Number(e.target.value) }
                        : null,
                    )
                  }
                >
                  <MenuItem value="0">Mon</MenuItem>
                  <MenuItem value="1">Tue</MenuItem>
                  <MenuItem value="2">Wed</MenuItem>
                  <MenuItem value="3">Thu</MenuItem>
                  <MenuItem value="4">Fri</MenuItem>
                </Select>
              </FormControl>
            )}

            {(scheduleDraft?.frequency === 'MONTHLY' || scheduleDraft?.frequency === 'QUARTERLY') && (
              <FormControl sx={{ width: { xs: '100%', md: 260 } }}>
                <InputLabel id="sched-dom-label">Day of month</InputLabel>
                <Select
                  labelId="sched-dom-label"
                  label="Day of month"
                  value={String(scheduleDraft.day_of_month ?? 'LAST')}
                  onChange={(e) => {
                    const v = String(e.target.value)
                    setScheduleDraft((prev) =>
                      prev
                        ? { ...prev, day_of_month: v === 'LAST' ? 'LAST' : Number(v) }
                        : null,
                    )
                  }}
                >
                  <MenuItem value="LAST">Last day</MenuItem>
                  {[1, 5, 10, 15, 20, 25].map((d) => (
                    <MenuItem key={d} value={String(d)}>
                      {d}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            {scheduleDraft?.frequency === 'CUSTOM_DAYS' && (
              <TextField
                label="Every N days"
                value={String(scheduleDraft.interval_days ?? 30)}
                onChange={(e) =>
                  setScheduleDraft((prev) =>
                    prev
                      ? { ...prev, interval_days: Number(e.target.value) }
                      : null,
                  )
                }
                sx={{ width: { xs: '100%', md: 260 } }}
              />
            )}

            <FormControl sx={{ width: { xs: '100%', md: 260 } }}>
              <InputLabel id="sched-roll-label">Weekend adjustment</InputLabel>
              <Select
                labelId="sched-roll-label"
                label="Weekend adjustment"
                value={scheduleDraft?.roll_to_trading_day ?? 'NEXT'}
                onChange={(e) =>
                  setScheduleDraft((prev) =>
                    prev
                      ? {
                          ...prev,
                          roll_to_trading_day: String(e.target.value) as RebalanceScheduleConfig['roll_to_trading_day'],
                        }
                      : null,
                  )
                }
              >
                <MenuItem value="NEXT">Move to next weekday</MenuItem>
                <MenuItem value="PREV">Move to previous weekday</MenuItem>
                <MenuItem value="NONE">No adjustment</MenuItem>
              </Select>
            </FormControl>

            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="contained"
                disabled={busy || !scheduleDraft}
                onClick={() => void saveSchedule()}
              >
                Save schedule
              </Button>
              {error && <Typography color="error">{error}</Typography>}
            </Stack>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>

      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Rebalance help</DialogTitle>
        <DialogContent dividers>
          {helpTabs.length > 1 ? (
            <Tabs
              value={helpTab}
              onChange={(_e, v) => setHelpTab(String(v))}
              variant="scrollable"
              scrollButtons="auto"
              sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
            >
              {helpTabs.map((t) => (
                <Tab key={t} label={t} value={t} />
              ))}
            </Tabs>
          ) : null}
          <MarkdownLite text={helpSections[helpTab] ?? helpSections.Overview ?? rebalanceHelpText} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Dialog>
  )
}
