import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import Autocomplete from '@mui/material/Autocomplete'
import {
  DataGrid,
  GridLogicOperator,
  GridToolbar,
  type GridColDef,
  type GridColumnVisibilityModel,
} from '@mui/x-data-grid'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { DslHelpDialog } from '../components/DslHelpDialog'
import { DslEditor } from '../components/DslEditor'
import type { AlertVariableDef } from '../services/alertsV3'
import {
  ALERT_V3_METRICS,
  ALERT_V3_SOURCES,
  ALERT_V3_TIMEFRAMES,
} from '../services/alertsV3Constants'
import { useCustomIndicators } from '../hooks/useCustomIndicators'
import { listGroups, type Group } from '../services/groups'
import {
  createGroupFromScreenerRun,
  cleanupScreenerRuns,
  deleteScreenerRun,
  getScreenerRun,
  listScreenerRuns,
  runScreener,
  type ScreenerRow,
  type ScreenerRun,
} from '../services/screenerV3'
import {
  getSignalStrategyVersion,
  listSignalStrategies,
  listSignalStrategyVersions,
  type SignalStrategy,
  type SignalStrategyVersion,
} from '../services/signalStrategies'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

type ConditionRow = { lhs: string; op: string; rhs: string }

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

const DEFAULT_CONDITION_ROWS: ConditionRow[] = [{ lhs: '', op: '>', rhs: '' }]

const SCREENER_LEFT_PANEL_WIDTH_STORAGE_KEY = 'st_screener_left_panel_width_v1'
const DEFAULT_LEFT_PANEL_WIDTH = 760
const SCREENER_RESULTS_COLUMN_VISIBILITY_STORAGE_KEY =
  'st_screener_results_column_visibility_v1'
const SCREENER_RUNS_RETENTION_STORAGE_KEY = 'st_screener_runs_retention_v1'

type ScreenerRunsRetentionSettings = {
  maxRuns: number
  maxDays: number
  autoCleanup: boolean
}

function loadRunsRetentionSettings(): ScreenerRunsRetentionSettings {
  try {
    const raw = window.localStorage.getItem(SCREENER_RUNS_RETENTION_STORAGE_KEY)
    if (!raw) {
      return { maxRuns: 50, maxDays: 14, autoCleanup: false }
    }
    const parsed = JSON.parse(raw) as Partial<ScreenerRunsRetentionSettings>
    return {
      maxRuns: typeof parsed.maxRuns === 'number' ? parsed.maxRuns : 50,
      maxDays: typeof parsed.maxDays === 'number' ? parsed.maxDays : 14,
      autoCleanup: typeof parsed.autoCleanup === 'boolean' ? parsed.autoCleanup : false,
    }
  } catch {
    return { maxRuns: 50, maxDays: 14, autoCleanup: false }
  }
}

function saveRunsRetentionSettings(next: ScreenerRunsRetentionSettings): void {
  try {
    window.localStorage.setItem(
      SCREENER_RUNS_RETENTION_STORAGE_KEY,
      JSON.stringify(next),
    )
  } catch {
    // ignore
  }
}

const DEFAULT_SCREENER_COLUMN_VISIBILITY: GridColumnVisibilityModel = {
  // Useful for debugging, but often empty; keep available via Columns menu.
  missing_data: false,
  error: false,
}

const CONDITION_OPS = [
  { value: '>', label: '>' },
  { value: '>=', label: '>=' },
  { value: '<', label: '<' },
  { value: '<=', label: '<=' },
  { value: '==', label: '==' },
  { value: '!=', label: '!=' },
  { value: 'CROSSES_ABOVE', label: 'CROSSES_ABOVE' },
  { value: 'CROSSES_BELOW', label: 'CROSSES_BELOW' },
  { value: 'MOVING_UP', label: 'MOVING_UP' },
  { value: 'MOVING_DOWN', label: 'MOVING_DOWN' },
]

function splitInlineDslVariables(dsl: string): {
  inlineVariables: Array<{ name: string; dsl: string }>
  conditionDsl: string
} {
  const inlineVariables: Array<{ name: string; dsl: string }> = []
  const conditionLines: string[] = []

  const isValidIdent = (s: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(s)

  const stripInlineComments = (line: string) => {
    let inSingle = false
    let inDouble = false
    let out = ''
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i]
      const next = i + 1 < line.length ? line[i + 1] : ''

      if (ch === "'" && !inDouble) {
        inSingle = !inSingle
        out += ch
        continue
      }
      if (ch === '"' && !inSingle) {
        inDouble = !inDouble
        out += ch
        continue
      }

      if (!inSingle && !inDouble) {
        if (ch === '#') break
        if (ch === '/' && next === '/') break
      }

      out += ch
    }
    return out.trim()
  }

  const parseAssignment = (line: string) => {
    // Only treat `NAME = expr` as an assignment.
    // Do NOT treat `==`, `>=`, `<=`, `!=` as assignment.
    let i = 0
    while (i < line.length && /\s/.test(line[i])) i += 1
    const start = i
    if (i >= line.length) return null
    const first = line[i]
    if (!(/[A-Za-z_]/.test(first))) return null
    i += 1
    while (i < line.length && /[A-Za-z0-9_]/.test(line[i])) i += 1
    const name = line.slice(start, i)
    let j = i
    while (j < line.length && /\s/.test(line[j])) j += 1
    if (j >= line.length || line[j] !== '=') return null
    if (j + 1 < line.length && line[j + 1] === '=') return null
    const rhs = line.slice(j + 1).trim()
    if (!name || !rhs || !isValidIdent(name)) return null
    return { name, rhs }
  }

  for (const rawLine of dsl.split(/\r?\n/)) {
    const line = stripInlineComments(rawLine)
    if (!line) continue

    const assignment = parseAssignment(line)
    if (assignment) {
      inlineVariables.push({ name: assignment.name, dsl: assignment.rhs })
      continue
    }

    conditionLines.push(line)
  }

  return {
    inlineVariables,
    conditionDsl: conditionLines.join(' ').trim(),
  }
}

function buildDslFromRows(join: 'AND' | 'OR', rows: ConditionRow[]): string {
  const parts = rows
    .map((r) => {
      const lhs = r.lhs.trim()
      const rhs = r.rhs.trim()
      const op = (r.op || '').trim()
      if (!lhs || !rhs || !op) return null
      return `(${lhs} ${op} ${rhs})`
    })
    .filter((v): v is string => !!v)
  return parts.join(` ${join} `)
}

export function ScreenerPage() {
  const { displayTimeZone } = useTimeSettings()
  const navigate = useNavigate()
  const [groups, setGroups] = useState<Group[]>([])
  const [loadingGroups, setLoadingGroups] = useState(false)
  const [groupsError, setGroupsError] = useState<string | null>(null)

  const [includeHoldings, setIncludeHoldings] = useState(true)
  const [selectedGroups, setSelectedGroups] = useState<Group[]>([])

  const [variables, setVariables] = useState<AlertVariableDef[]>([])
  const [conditionTab, setConditionTab] = useState<0 | 1>(0)
  const [conditionJoin, setConditionJoin] = useState<'AND' | 'OR'>('AND')
  const [conditionRows, setConditionRows] =
    useState<ConditionRow[]>(DEFAULT_CONDITION_ROWS)
  const [conditionDsl, setConditionDsl] = useState('')
  const [helpOpen, setHelpOpen] = useState(false)
  const [evaluationCadence, setEvaluationCadence] = useState<string>('')

  // Saved strategy (optional)
  const [useSavedStrategy, setUseSavedStrategy] = useState(false)
  const [strategies, setStrategies] = useState<SignalStrategy[]>([])
  const [strategiesLoading, setStrategiesLoading] = useState(false)
  const [strategiesError, setStrategiesError] = useState<string | null>(null)
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(null)
  const [strategyVersions, setStrategyVersions] = useState<SignalStrategyVersion[]>([])
  const [selectedStrategyVersionId, setSelectedStrategyVersionId] = useState<number | null>(null)
  const [selectedStrategyOutput, setSelectedStrategyOutput] = useState<string | null>(null)
  const [strategyParams, setStrategyParams] = useState<Record<string, unknown>>({})

  const [run, setRun] = useState<ScreenerRun | null>(null)
  const [runLoading, setRunLoading] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  const [matchedOnly, setMatchedOnly] = useState(true)
  const [showVariables, setShowVariables] = useState(false)

  type RightTab = 'results' | 'runs'
  const [rightTab, setRightTab] = useState<RightTab>('results')

  const [runs, setRuns] = useState<ScreenerRun[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [runsInfo, setRunsInfo] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)

  const [retention, setRetention] = useState<ScreenerRunsRetentionSettings>(() =>
    loadRunsRetentionSettings(),
  )
  const [cleanupLoading, setCleanupLoading] = useState(false)
  const lastAutoCleanupRunId = useRef<number | null>(null)

  const [columnVisibilityModel, setColumnVisibilityModel] =
    useState<GridColumnVisibilityModel>(() => {
      if (typeof window === 'undefined') return DEFAULT_SCREENER_COLUMN_VISIBILITY
      try {
        const raw = window.localStorage.getItem(
          SCREENER_RESULTS_COLUMN_VISIBILITY_STORAGE_KEY,
        )
        if (!raw) return DEFAULT_SCREENER_COLUMN_VISIBILITY
        const parsed = JSON.parse(raw) as GridColumnVisibilityModel
        return { ...DEFAULT_SCREENER_COLUMN_VISIBILITY, ...parsed }
      } catch {
        return DEFAULT_SCREENER_COLUMN_VISIBILITY
      }
    })

  const [createGroupOpen, setCreateGroupOpen] = useState(false)
  const [createGroupName, setCreateGroupName] = useState('')
  const [createGroupSubmitting, setCreateGroupSubmitting] = useState(false)
  const [createGroupError, setCreateGroupError] = useState<string | null>(null)

  // Resizable panel state (like Groups page)
  const containerRef = useRef<HTMLDivElement>(null)
  const [leftPanelWidth, setLeftPanelWidth] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_LEFT_PANEL_WIDTH
    try {
      const raw = window.localStorage.getItem(SCREENER_LEFT_PANEL_WIDTH_STORAGE_KEY)
      const parsed = raw != null ? Number(raw) : Number.NaN
      return Number.isFinite(parsed) && parsed >= 300 ? parsed : DEFAULT_LEFT_PANEL_WIDTH
    } catch {
      return DEFAULT_LEFT_PANEL_WIDTH
    }
  })
  const [isResizing, setIsResizing] = useState(false)

  const startResizing = useCallback(() => setIsResizing(true), [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const newWidth = e.clientX - rect.left
      if (newWidth > 300 && newWidth < rect.width - 300) setLeftPanelWidth(newWidth)
    }

    const handleMouseUp = () => setIsResizing(false)

    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    } else {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (isResizing) return
    try {
      window.localStorage.setItem(
        SCREENER_LEFT_PANEL_WIDTH_STORAGE_KEY,
        String(Math.round(leftPanelWidth)),
      )
    } catch {
      // Ignore persistence errors.
    }
  }, [isResizing, leftPanelWidth])

  const builderDsl = useMemo(
    () => buildDslFromRows(conditionJoin, conditionRows),
    [conditionJoin, conditionRows],
  )

  const inlineDsl = useMemo(() => splitInlineDslVariables(conditionDsl), [conditionDsl])

  const activeStrategyVersion = useMemo(() => {
    if (selectedStrategyVersionId == null) return null
    return strategyVersions.find((v) => v.id === selectedStrategyVersionId) ?? null
  }, [selectedStrategyVersionId, strategyVersions])

  useEffect(() => {
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
  }, [activeStrategyVersion?.id, selectedStrategyOutput, useSavedStrategy])

  useEffect(() => {
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
  }, [activeStrategyVersion?.id, selectedStrategyOutput, useSavedStrategy])

  const effectiveVariables = useMemo(() => {
    const fromInline = conditionTab === 1 ? inlineDsl.inlineVariables : []
    const fromUi = variables
      .map((v) => ({ ...v, name: (v.name || '').trim() }))
      .filter((v) => v.name)

    const seen = new Set<string>()
    const ordered: AlertVariableDef[] = []

    for (const v of fromInline) {
      const key = v.name.toUpperCase()
      if (seen.has(key)) continue
      seen.add(key)
      ordered.push({ name: v.name.trim(), dsl: v.dsl })
    }

    for (const v of fromUi) {
      const key = v.name.toUpperCase()
      if (seen.has(key)) continue
      seen.add(key)
      ordered.push(v)
    }

    return ordered
  }, [conditionTab, inlineDsl.inlineVariables, variables])

  const variableKindOf = (v: AlertVariableDef): VariableKind => {
    if (v.kind) return v.kind as VariableKind
    return 'DSL'
  }

  const varParams = (v: AlertVariableDef): Record<string, any> => {
    return (v.params ?? {}) as Record<string, any>
  }

  const updateVar = (idx: number, next: AlertVariableDef) => {
    if (useSavedStrategy) return
    setVariables((prev) => prev.map((v, i) => (i === idx ? next : v)))
  }

  const setVariableKind = (idx: number, kind: VariableKind) => {
    if (useSavedStrategy) return
    setVariables((prev) =>
      prev.map((v, i) => {
        if (i !== idx) return v
        const name = v.name
        if (kind === 'DSL') return { name, dsl: v.dsl ?? '' }
        if (kind === 'METRIC')
          return { name, kind: 'METRIC', params: { metric: ALERT_V3_METRICS[0] } }
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
        if (
          kind === 'SMA' ||
          kind === 'EMA' ||
          kind === 'RSI' ||
          kind === 'STDDEV'
        ) {
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

  const {
    customIndicators,
    loading: customIndicatorsLoading,
    error: customIndicatorsError,
    refresh: refreshCustomIndicators,
  } = useCustomIndicators({
    enabled: true,
  })

  const operandOptions = useMemo(() => {
    const vars = effectiveVariables
      .map((v) => (v.name || '').trim())
      .filter((x) => x.length > 0)
    return Array.from(new Set([...vars, ...ALERT_V3_METRICS]))
  }, [effectiveVariables])

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoadingGroups(true)
        setGroupsError(null)
        const res = await listGroups()
        if (!active) return
        setGroups(res)
      } catch (err) {
        if (!active) return
        setGroupsError(err instanceof Error ? err.message : 'Failed to load groups')
      } finally {
        if (!active) return
        setLoadingGroups(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
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
        setStrategiesError(err instanceof Error ? err.message : 'Failed to load strategies')
      } finally {
        if (!active) return
        setStrategiesLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
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
  }, [selectedStrategyId])

  useEffect(() => {
    if (!run || run.status !== 'RUNNING') return
    let active = true
    const tick = async () => {
      try {
        const next = await getScreenerRun(run.id, { includeRows: false })
        if (!active) return
        setRun(next)
        if (next.status === 'DONE') {
          const done = await getScreenerRun(run.id, { includeRows: true })
          if (!active) return
          setRun(done)
        }
      } catch (err) {
        if (!active) return
        setRunError(err instanceof Error ? err.message : 'Failed to poll run')
      }
    }

    const id = window.setInterval(() => void tick(), 1200)
    void tick()
    return () => {
      active = false
      window.clearInterval(id)
    }
  }, [run])

  const refreshRuns = useCallback(async () => {
    setRunsLoading(true)
    setRunsError(null)
    try {
      const res = await listScreenerRuns({ limit: 200, offset: 0, includeRows: false })
      setRuns(res)
    } catch (err) {
      setRunsError(err instanceof Error ? err.message : 'Failed to load runs')
    } finally {
      setRunsLoading(false)
    }
  }, [])

  useEffect(() => {
    saveRunsRetentionSettings(retention)
  }, [retention])

  const doCleanupRuns = useCallback(
    async (opts?: { dryRun?: boolean }) => {
      setCleanupLoading(true)
      setRunsInfo(null)
      setRunsError(null)
      try {
        const maxRuns = Number.isFinite(retention.maxRuns) ? retention.maxRuns : 0
        const maxDays = Number.isFinite(retention.maxDays) ? retention.maxDays : 0
        const res = await cleanupScreenerRuns({
          max_runs: maxRuns > 0 ? maxRuns : null,
          max_days: maxDays > 0 ? maxDays : null,
          dry_run: opts?.dryRun ?? false,
        })
        setRunsInfo(
          `${opts?.dryRun ? 'Would delete' : 'Deleted'} ${res.deleted}; remaining ${res.remaining}.`,
        )
        await refreshRuns()
      } catch (err) {
        setRunsError(err instanceof Error ? err.message : 'Failed to cleanup runs')
      } finally {
        setCleanupLoading(false)
      }
    },
    [refreshRuns, retention.maxDays, retention.maxRuns],
  )

  useEffect(() => {
    if (rightTab !== 'runs') return
    void refreshRuns()
  }, [rightTab, refreshRuns])

  useEffect(() => {
    if (!retention.autoCleanup) return
    if (!run) return
    if (run.status !== 'DONE' && run.status !== 'ERROR') return
    if (lastAutoCleanupRunId.current === run.id) return
    lastAutoCleanupRunId.current = run.id
    void doCleanupRuns()
    void refreshRuns()
  }, [doCleanupRuns, refreshRuns, retention.autoCleanup, run])

  const handleAddVariable = () => {
    setVariables((current) => [...current, { name: '', dsl: '' }])
  }

  const handleRun = async () => {
    const groupIds = selectedGroups.map((g) => g.id)
    const rawDsl = conditionTab === 0 ? builderDsl : conditionDsl
    const extracted =
      conditionTab === 1 ? inlineDsl.conditionDsl : rawDsl
    const dsl = (conditionTab === 0 ? builderDsl : extracted).trim()
    if (!dsl) {
      setRunError('Condition is empty.')
      return
    }
    if (!includeHoldings && groupIds.length === 0) {
      setRunError('Select Holdings and/or at least one group.')
      return
    }
    if (useSavedStrategy && selectedStrategyVersionId == null) {
      setRunError('Select a saved strategy (and version) first.')
      return
    }

    setRunLoading(true)
    setRunError(null)
    try {
      const res = await runScreener({
        include_holdings: includeHoldings,
        group_ids: groupIds,
        variables: effectiveVariables,
        condition_dsl: dsl,
        evaluation_cadence: evaluationCadence.trim() || null,
        signal_strategy_version_id: useSavedStrategy ? selectedStrategyVersionId : null,
        signal_strategy_output: useSavedStrategy ? selectedStrategyOutput : null,
        signal_strategy_params: useSavedStrategy ? strategyParams : {},
      })
      setRun(res)
      if (res.status === 'DONE' && !res.rows) {
        const done = await getScreenerRun(res.id, { includeRows: true })
        setRun(done)
      }
    } catch (err) {
      setRun(null)
      setRunError(err instanceof Error ? err.message : 'Failed to run screener')
    } finally {
      setRunLoading(false)
    }
  }

  const filteredRows: ScreenerRow[] = useMemo(() => {
    const rows = run?.rows ?? []
    if (!matchedOnly) return rows
    return rows.filter((r) => r.matched)
  }, [run, matchedOnly])

  const variableColumns: GridColDef[] = useMemo(() => {
    if (!showVariables) return []
    const keys = effectiveVariables.map((v) => v.name).filter(Boolean)
    return keys.map((name) => {
      const display = String(name)
      const upper = display.toUpperCase()
      return {
        field: `var_${upper}`,
        headerName: display,
        width: 140,
        valueGetter: (_value: any, row: any) =>
          ((row as ScreenerRow | undefined)?.variables ?? {})[upper] ??
          ((row as ScreenerRow | undefined)?.variables ?? {})[display] ??
          null,
      } as GridColDef
    })
  }, [showVariables, effectiveVariables])

  const columns: GridColDef[] = useMemo(
    () => {
      const base: GridColDef[] = [
        { field: 'symbol', headerName: 'Symbol', width: 140 },
        { field: 'exchange', headerName: 'Exch', width: 90 },
        {
          field: 'matched',
          headerName: 'Match',
          width: 90,
          renderCell: (params: any) => (params.value ? 'YES' : '—'),
        },
        {
          field: 'last_price',
          headerName: 'Last',
          width: 110,
          renderCell: (params: any) =>
            params.value != null && Number.isFinite(Number(params.value))
              ? Number(params.value).toFixed(2)
              : '—',
        },
      ]

      const diagnostics: GridColDef[] = [
        {
          field: 'missing_data',
          headerName: 'Missing',
          width: 110,
          renderCell: (params: any) => (params.value ? 'YES' : '—'),
        },
        {
          field: 'error',
          headerName: 'Error',
          width: 260,
          renderCell: (params: any) =>
            params.value ? (
              <Typography variant="caption" color="error">
                {String(params.value)}
              </Typography>
            ) : (
              '—'
            ),
        },
      ]

      // Keep Missing/Error at the end.
      return [...base, ...variableColumns, ...diagnostics]
    },
    [variableColumns],
  )

  const gridRows = useMemo(
    () =>
      filteredRows.map((r) => ({
        id: `${r.exchange}:${r.symbol}`,
        ...r,
      })),
    [filteredRows],
  )

  const groupNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const g of groups) m.set(g.id, g.name)
    return m
  }, [groups])

  const formatDateTime = useCallback((iso?: string | null): string => {
    if (!iso) return '—'
    const out = formatInDisplayTimeZone(iso, displayTimeZone)
    return out || '—'
  }, [displayTimeZone])

  const universeLabel = useCallback(
    (r: ScreenerRun): string => {
      const parts: string[] = []
      if (r.include_holdings) parts.push('Holdings')
      const ids = r.group_ids ?? []
      if (ids.length > 0) {
        const names = ids
          .map((id) => groupNameById.get(id) ?? `#${id}`)
          .filter(Boolean)
        parts.push(names.join(', '))
      }
      return parts.length > 0 ? parts.join(' + ') : '—'
    },
    [groupNameById],
  )

  const runRows = useMemo(() => runs.map((r) => ({ ...r, id: r.id })), [runs])

  const loadRunIntoEditor = useCallback(
    async (r: ScreenerRun) => {
      setRunsInfo(null)
      setRunsError(null)
      setIncludeHoldings(Boolean(r.include_holdings))
      const ids = new Set<number>((r.group_ids ?? []).map((x) => Number(x)))
      setSelectedGroups(groups.filter((g) => ids.has(g.id)))
      setEvaluationCadence(String(r.evaluation_cadence ?? ''))
      setVariables(Array.isArray(r.variables) ? (r.variables as AlertVariableDef[]) : [])
      setConditionTab(1)
      setConditionDsl(String(r.condition_dsl ?? ''))

      if (r.signal_strategy_version_id != null) {
        try {
          const v = await getSignalStrategyVersion(Number(r.signal_strategy_version_id))
          setUseSavedStrategy(true)
          setSelectedStrategyId(v.strategy_id)
          setSelectedStrategyVersionId(Number(r.signal_strategy_version_id))
          setSelectedStrategyOutput(r.signal_strategy_output ?? null)
          setStrategyParams((r.signal_strategy_params ?? {}) as Record<string, unknown>)
        } catch (err) {
          setRunsError(
            err instanceof Error
              ? err.message
              : 'Failed to load saved strategy version for this run',
          )
        }
      } else {
        setUseSavedStrategy(false)
        setSelectedStrategyId(null)
        setSelectedStrategyVersionId(null)
        setSelectedStrategyOutput(null)
        setStrategyParams({})
      }

      setRunsInfo(`Loaded run #${r.id} into editor.`)
    },
    [groups],
  )

  const viewRunResults = useCallback(async (runId: number) => {
    setRunError(null)
    setRunLoading(true)
    try {
      const full = await getScreenerRun(runId, { includeRows: true })
      setRun(full)
      setSelectedRunId(runId)
      setRightTab('results')
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'Failed to load run results')
    } finally {
      setRunLoading(false)
    }
  }, [])

  const openRunsTab = useCallback(
    async (runId?: number) => {
      setRightTab('runs')
      if (runId != null) setSelectedRunId(runId)
      await refreshRuns()
    },
    [refreshRuns],
  )

  const runsColumns: GridColDef[] = useMemo(() => {
    const cols: GridColDef[] = [
      {
        field: 'id',
        headerName: 'Run #',
        width: 90,
      },
      {
        field: 'created_at',
        headerName: 'Created',
        width: 190,
        valueGetter: (_v, row: any) => formatDateTime((row as ScreenerRun).created_at),
      },
      { field: 'status', headerName: 'Status', width: 110 },
      {
        field: 'universe',
        headerName: 'Universe',
        flex: 1,
        minWidth: 220,
        valueGetter: (_v, row: any) => universeLabel(row as ScreenerRun),
      },
      { field: 'evaluation_cadence', headerName: 'Cadence', width: 110 },
      { field: 'matched_symbols', headerName: 'Matched', width: 110 },
      { field: 'total_symbols', headerName: 'Total', width: 100 },
      { field: 'missing_symbols', headerName: 'Missing', width: 110 },
      {
        field: 'strategy',
        headerName: 'Mode',
        width: 220,
        valueGetter: (_v, row: any) => {
          const r = row as ScreenerRun
          if (r.signal_strategy_version_id != null) {
            const out = r.signal_strategy_output ? `:${r.signal_strategy_output}` : ''
            return `Strategy v${r.signal_strategy_version_id}${out}`
          }
          return 'DSL'
        },
      },
      {
        field: 'condition_dsl',
        headerName: 'DSL',
        flex: 2,
        minWidth: 320,
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 260,
        sortable: false,
        filterable: false,
        renderCell: (params: any) => {
          const r = params.row as ScreenerRun
          return (
            <Stack direction="row" spacing={1}>
              <Button size="small" onClick={() => void viewRunResults(r.id)}>
                View
              </Button>
              <Button size="small" onClick={() => void loadRunIntoEditor(r)}>
                Load
              </Button>
              <Button
                size="small"
                color="error"
                onClick={async () => {
                  const ok = window.confirm(`Delete screener run #${r.id}?`)
                  if (!ok) return
                  try {
                    await deleteScreenerRun(r.id)
                    setRunsInfo(`Deleted run #${r.id}.`)
                    await refreshRuns()
                  } catch (err) {
                    setRunsError(err instanceof Error ? err.message : 'Failed to delete run')
                  }
                }}
              >
                Delete
              </Button>
            </Stack>
          )
        },
      },
    ]
    return cols
  }, [formatDateTime, loadRunIntoEditor, refreshRuns, universeLabel, viewRunResults])

  const handleCreateGroup = async () => {
    if (!run) return
    const name = createGroupName.trim()
    if (!name) {
      setCreateGroupError('Group name is required.')
      return
    }
    setCreateGroupSubmitting(true)
    setCreateGroupError(null)
    try {
      const created = await createGroupFromScreenerRun(run.id, {
        name,
        kind: 'WATCHLIST',
        description: `Created from screener run #${run.id}`,
      })
      setCreateGroupOpen(false)
      setCreateGroupName('')
      navigate(`/groups`)
      // Future improvement: deep-link into group details.
      void created
    } catch (err) {
      setCreateGroupError(
        err instanceof Error ? err.message : 'Failed to create group',
      )
    } finally {
      setCreateGroupSubmitting(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Screener
      </Typography>

      <Box
        ref={containerRef}
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          gap: 0,
          alignItems: 'stretch',
        }}
      >
        <Box sx={{ width: { xs: '100%', md: leftPanelWidth }, minWidth: 300, flexShrink: 0 }}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <Autocomplete
                multiple
                options={groups}
                loading={loadingGroups}
                getOptionLabel={(g) => g.name}
                value={selectedGroups}
                onChange={(_e, value) => setSelectedGroups(value)}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Groups (union)"
                    helperText={groupsError || 'Select one or more groups (deduped).'}
                    error={!!groupsError}
                  />
                )}
                sx={{ flex: 1, minWidth: 320 }}
              />
              <Stack spacing={1} sx={{ minWidth: 240 }}>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={includeHoldings}
                      onChange={(e) => setIncludeHoldings(e.target.checked)}
                    />
                  }
                  label="Include Holdings (Zerodha)"
                />
                <TextField
                  label="Evaluation cadence (optional)"
                  size="small"
                  value={evaluationCadence}
                  onChange={(e) => setEvaluationCadence(e.target.value)}
                  helperText="Leave blank to auto-pick from referenced timeframes."
                />
              </Stack>
	            </Stack>

              <Box>
                <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={useSavedStrategy}
                        onChange={(e) => {
                          const next = e.target.checked
                          setUseSavedStrategy(next)
                          if (next) setConditionTab(1)
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

	            <Box
                sx={{
                  pointerEvents: useSavedStrategy ? 'none' : 'auto',
                  opacity: useSavedStrategy ? 0.7 : 1,
                }}
              >
	              <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
	                <Typography variant="subtitle2">Variables</Typography>
	                <Button size="small" onClick={handleAddVariable}>
	                  Add variable
	                </Button>
	              </Stack>
              {variables.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  Optional: define readable aliases like <code>RSI_1D_14</code> ={' '}
                  <code>RSI(close, 14, &quot;1d&quot;)</code>.
                </Typography>
              ) : (
                <Stack spacing={1}>
                  {variables.map((v, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        display: 'flex',
                        gap: 1,
                        flexWrap: 'wrap',
                        alignItems: 'flex-start',
                      }}
                    >
                      <TextField
                        label="Name"
                        size="small"
                        value={v.name}
                        onChange={(e) => updateVar(idx, { ...v, name: e.target.value })}
                        sx={{ width: 200 }}
                      />
                      <TextField
                        label="Type"
                        select
                        size="small"
                        value={variableKindOf(v)}
                        onChange={(e) => setVariableKind(idx, e.target.value as VariableKind)}
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
                            updateVar(idx, {
                              ...v,
                              kind: 'METRIC',
                              params: { metric: e.target.value },
                            })
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
                      {['PRICE', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME'].includes(
                        variableKindOf(v),
                      ) && (
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
                          <Box
                            sx={{
                              display: 'flex',
                              gap: 1,
                              flexWrap: 'wrap',
                              alignItems: 'center',
                            }}
                          >
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
                                      : !customIndicatorsLoading &&
                                          customIndicators.length === 0
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
                            value={
                              (Array.isArray(varParams(v).args) ? varParams(v).args : []).join(
                                ', ',
                              )
                            }
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
                          setVariables((cur) => cur.filter((_x, i) => i !== idx))
                        }
                      >
                        Remove
                      </Button>
                    </Box>
                  ))}
                </Stack>
              )}
            </Box>

            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Condition
              </Typography>
	              <Tabs
	                value={conditionTab}
	                onChange={(_e, v) => {
	                  if (useSavedStrategy) return
	                  setConditionTab(v)
	                }}
	                sx={{ mb: 1 }}
	              >
	                <Tab label="Builder" disabled={useSavedStrategy} />
	                <Tab label="Advanced (DSL)" />
	              </Tabs>

              {conditionTab === 0 ? (
                <Stack spacing={1}>
                  <TextField
                    select
                    size="small"
                    label="Join"
                    value={conditionJoin}
                    onChange={(e) =>
                      setConditionJoin(e.target.value === 'OR' ? 'OR' : 'AND')
                    }
                    sx={{ width: 180 }}
                  >
                    <MenuItem value="AND">AND</MenuItem>
                    <MenuItem value="OR">OR</MenuItem>
                  </TextField>
	                  {conditionRows.map((r, idx) => (
	                    <Stack
	                      key={idx}
	                      direction={{ xs: 'column', md: 'row' }}
	                      spacing={1}
	                      alignItems="center"
	                    >
                      <Autocomplete
                        freeSolo
                        options={operandOptions}
                        value={r.lhs}
                        onChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((row, i) =>
                              i === idx ? { ...row, lhs: String(v ?? '') } : row,
                            ),
                          )
                        }
                        onInputChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((row, i) =>
                              i === idx ? { ...row, lhs: v } : row,
                            ),
                          )
                        }
	                        renderInput={(params) => (
	                          <TextField
	                            {...params}
	                            label="LHS"
	                            size="small"
	                            sx={{ flex: 1, minWidth: 200 }}
	                          />
	                        )}
                      />
                      <TextField
                        label="Op"
                        size="small"
                        select
	                        value={r.op}
                        onChange={(e) => {
                          const next = e.target.value
                          setConditionRows((cur) =>
                            cur.map((row, i) =>
                              i === idx ? { ...row, op: next } : row,
                            ),
	                          )
	                        }}
	                        sx={{ minWidth: 200, maxWidth: 240 }}
                      >
                        {CONDITION_OPS.map((o) => (
                          <MenuItem key={o.value} value={o.value}>
                            {o.label}
                          </MenuItem>
                        ))}
                      </TextField>
                      <Autocomplete
                        freeSolo
                        options={operandOptions}
                        value={r.rhs}
                        onChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((row, i) =>
                              i === idx ? { ...row, rhs: String(v ?? '') } : row,
                            ),
                          )
                        }
                        onInputChange={(_e, v) =>
                          setConditionRows((prev) =>
                            prev.map((row, i) =>
                              i === idx ? { ...row, rhs: v } : row,
                            ),
                          )
                        }
	                        renderInput={(params) => (
	                          <TextField
	                            {...params}
	                            label="RHS"
	                            size="small"
	                            sx={{ flex: 1, minWidth: 200 }}
                            helperText={
                              r.op === 'MOVING_UP' || r.op === 'MOVING_DOWN'
                                ? 'RHS must be numeric'
                                : undefined
                            }
                          />
                        )}
                      />
                      <Button
                        color="error"
                        disabled={conditionRows.length === 1}
                        onClick={() =>
                          setConditionRows((cur) => cur.filter((_x, i) => i !== idx))
                        }
                      >
                        Remove
                      </Button>
                    </Stack>
                  ))}
                  <Stack direction="row" spacing={1}>
                    <Button
                      size="small"
                      onClick={() =>
                        setConditionRows((cur) => [
                          ...cur,
                          { lhs: '', op: '>', rhs: '' },
                        ])
                      }
                    >
                      Add condition
                    </Button>
                  </Stack>
                  <TextField
                    label="Expression preview"
                    value={builderDsl || ''}
                    size="small"
                    InputProps={{ readOnly: true }}
                    fullWidth
                  />
                </Stack>
              ) : (
                <Box>
                  <Stack direction="row" spacing={1} sx={{ mb: 0.5 }} alignItems="center">
                    <Typography variant="subtitle2">DSL expression</Typography>
                    <Box sx={{ flex: 1 }} />
                    <Tooltip title="Help: DSL syntax, functions, metrics">
                      <IconButton size="small" onClick={() => setHelpOpen(true)}>
                        <HelpOutlineIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Button
                      size="small"
                      variant="text"
                      disabled={!conditionDsl}
                      onClick={() => setConditionDsl('')}
                    >
                      Clear
                    </Button>
                  </Stack>
                  <DslEditor
                    languageId="st-dsl-screener-condition"
                    value={conditionDsl}
                    onChange={setConditionDsl}
                    operands={operandOptions}
                    customIndicators={customIndicators}
                    height={160}
                    onCtrlEnter={() => void handleRun()}
                  />
                  <Typography variant="caption" color="text.secondary">
                    Suggestions show as you type; press <code>Tab</code> to accept a snippet; press{' '}
                    <code>Ctrl</code>+<code>Enter</code> to run.
                  </Typography>
                </Box>
              )}
            </Box>

            <Stack direction="row" spacing={2} alignItems="center">
              <Button variant="contained" onClick={handleRun} disabled={runLoading}>
                {runLoading ? 'Running…' : 'Run screener'}
              </Button>
              {run && (
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <Button size="small" variant="text" onClick={() => void openRunsTab(run.id)}>
                    Run #{run.id}
                  </Button>
                  <Typography variant="body2" color="text.secondary">
                    — {run.status} — {run.matched_symbols}/{run.total_symbols} matched — missing{' '}
                    {run.missing_symbols}
                    {run.status === 'ERROR' && run.error ? ` — ${run.error}` : ''}
                  </Typography>
                </Stack>
              )}
              {runError && (
                <Typography variant="body2" color="error">
                  {runError}
                </Typography>
              )}
            </Stack>
          </Stack>
          </Paper>
        </Box>

        {/* Draggable Divider */}
        <Box
          onMouseDown={startResizing}
          sx={{
            width: 12,
            cursor: 'col-resize',
            display: { xs: 'none', md: 'flex' },
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            '&:hover .divider-line': {
              bgcolor: 'primary.main',
              height: '40px',
            },
          }}
        >
          <Box
            className="divider-line"
            sx={{
              width: 4,
              height: '24px',
              bgcolor: 'divider',
              borderRadius: 1,
              transition: 'all 0.2s',
            }}
          />
        </Box>

        <Box sx={{ flex: 1, minWidth: 300, display: 'flex', flexDirection: 'column' }}>
          <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
            <Stack spacing={1}>
              <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 0.5 }}>
                <Tabs
                  value={rightTab}
                  onChange={(_e, v) => setRightTab(v as RightTab)}
                  sx={{ minHeight: 36, '& .MuiTab-root': { minHeight: 36 } }}
                >
                  <Tab value="results" label="Results" />
                  <Tab
                    value="runs"
                    label={`Runs${runs.length > 0 ? ` (${runs.length})` : ''}`}
                  />
                </Tabs>
                <Box sx={{ flex: 1 }} />
                {rightTab === 'runs' ? (
                  <Tooltip title="Refresh runs list">
                    <IconButton size="small" onClick={() => void refreshRuns()}>
                      <RefreshIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                ) : null}
              </Stack>

              {rightTab === 'results' ? (
                <>
                  <Stack direction="row" spacing={2} sx={{ mb: 1 }} alignItems="center">
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={matchedOnly}
                          onChange={(e) => setMatchedOnly(e.target.checked)}
                        />
                      }
                      label="Matched only"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={showVariables}
                          onChange={(e) => setShowVariables(e.target.checked)}
                        />
                      }
                      label="Show variable values"
                    />
                    <Button
                      variant="outlined"
                      disabled={!run || run.status !== 'DONE' || run.matched_symbols === 0}
                      onClick={() => {
                        setCreateGroupError(null)
                        setCreateGroupOpen(true)
                      }}
                    >
                      Create group from matches
                    </Button>
                    <Box sx={{ flex: 1 }} />
                    <Button variant="text" onClick={() => void openRunsTab(run?.id)}>
                      Runs
                    </Button>
                    <Button variant="text" onClick={() => navigate('/groups')}>
                      Manage groups
                    </Button>
                  </Stack>

                  <Box sx={{ height: { xs: 560, lg: 720 }, width: '100%' }}>
                    <DataGrid
                      rows={gridRows}
                      columns={columns}
                      loading={runLoading || (run?.status === 'RUNNING')}
                      disableRowSelectionOnClick
                      columnVisibilityModel={columnVisibilityModel}
                      onColumnVisibilityModelChange={(model) => {
                        setColumnVisibilityModel(model)
                        try {
                          window.localStorage.setItem(
                            SCREENER_RESULTS_COLUMN_VISIBILITY_STORAGE_KEY,
                            JSON.stringify(model),
                          )
                        } catch {
                          // Ignore persistence errors.
                        }
                      }}
                      slots={{ toolbar: GridToolbar }}
                      slotProps={{
                        toolbar: {
                          showQuickFilter: true,
                          quickFilterProps: { debounceMs: 300 },
                        },
                        filterPanel: {
                          logicOperators: [GridLogicOperator.And],
                        },
                      }}
                      initialState={{
                        pagination: { paginationModel: { pageSize: 25 } },
                      }}
                      pageSizeOptions={[25, 50, 100]}
                      localeText={{
                        noRowsLabel: run ? 'No rows.' : 'Run a screener to see results.',
                      }}
                    />
                  </Box>
                </>
              ) : (
                <>
                  <Box
                    sx={{
                      p: 1.5,
                      border: 1,
                      borderColor: 'divider',
                      borderRadius: 1,
                    }}
                  >
                    <Stack
                      direction={{ xs: 'column', md: 'row' }}
                      spacing={2}
                      alignItems={{ xs: 'stretch', md: 'center' }}
                    >
                      <TextField
                        label="Keep last N runs"
                        size="small"
                        type="number"
                        value={retention.maxRuns}
                        onChange={(e) =>
                          setRetention((prev) => ({
                            ...prev,
                            maxRuns: Math.max(0, Number(e.target.value || 0)),
                          }))
                        }
                        helperText="0 disables this rule."
                        sx={{ width: 180 }}
                      />
                      <TextField
                        label="Keep last X days"
                        size="small"
                        type="number"
                        value={retention.maxDays}
                        onChange={(e) =>
                          setRetention((prev) => ({
                            ...prev,
                            maxDays: Math.max(0, Number(e.target.value || 0)),
                          }))
                        }
                        helperText="0 disables this rule."
                        sx={{ width: 180 }}
                      />
                      <FormControlLabel
                        control={
                          <Switch
                            checked={retention.autoCleanup}
                            onChange={(e) =>
                              setRetention((prev) => ({
                                ...prev,
                                autoCleanup: e.target.checked,
                              }))
                            }
                          />
                        }
                        label="Auto cleanup after run"
                      />
                      <Box sx={{ flex: 1 }} />
                      <Button
                        variant="outlined"
                        disabled={cleanupLoading}
                        onClick={() => void doCleanupRuns()}
                      >
                        {cleanupLoading ? 'Cleaning…' : 'Cleanup now'}
                      </Button>
                      <Button
                        variant="text"
                        disabled={cleanupLoading}
                        onClick={() => void doCleanupRuns({ dryRun: true })}
                      >
                        Dry run
                      </Button>
                    </Stack>
                    {runsInfo ? (
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        {runsInfo}
                      </Typography>
                    ) : null}
                    {runsError ? (
                      <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                        {runsError}
                      </Typography>
                    ) : null}
                  </Box>

                  <Box sx={{ height: { xs: 560, lg: 720 }, width: '100%' }}>
                    <DataGrid
                      rows={runRows}
                      columns={runsColumns}
                      loading={runsLoading}
                      disableRowSelectionOnClick
                      rowSelectionModel={selectedRunId != null ? [selectedRunId] : []}
                      onRowSelectionModelChange={(model) => {
                        const first = Array.isArray(model) ? model[0] : null
                        setSelectedRunId(first != null ? Number(first) : null)
                      }}
                      slots={{ toolbar: GridToolbar }}
                      slotProps={{
                        toolbar: {
                          showQuickFilter: true,
                          quickFilterProps: { debounceMs: 300 },
                        },
                        filterPanel: {
                          logicOperators: [GridLogicOperator.And],
                        },
                      }}
                      initialState={{
                        pagination: { paginationModel: { pageSize: 25 } },
                      }}
                      pageSizeOptions={[25, 50, 100]}
                      localeText={{
                        noRowsLabel: 'No past runs yet.',
                      }}
                    />
                  </Box>
                </>
              )}
            </Stack>
          </Paper>
        </Box>
      </Box>

      <Dialog open={createGroupOpen} onClose={() => setCreateGroupOpen(false)}>
        <DialogTitle>Create group from matches</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            label="Group name"
            value={createGroupName}
            onChange={(e) => setCreateGroupName(e.target.value)}
            fullWidth
            autoFocus
          />
          {createGroupError && (
            <Typography variant="body2" color="error" sx={{ mt: 1 }}>
              {createGroupError}
            </Typography>
          )}
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Creates a static snapshot group containing only matched symbols (symbol + exchange).
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setCreateGroupOpen(false)}
            disabled={createGroupSubmitting}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleCreateGroup}
            disabled={createGroupSubmitting}
          >
            {createGroupSubmitting ? 'Creating…' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <DslHelpDialog
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        context="screener"
      />
    </Box>
  )
}
