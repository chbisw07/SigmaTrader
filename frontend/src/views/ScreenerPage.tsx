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
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import Autocomplete from '@mui/material/Autocomplete'
import {
  DataGrid,
  type GridColDef,
} from '@mui/x-data-grid'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

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
  getScreenerRun,
  runScreener,
  type ScreenerRow,
  type ScreenerRun,
} from '../services/screenerV3'

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
  | 'MAX'
  | 'MIN'
  | 'AVG'
  | 'SUM'
  | 'RET'
  | 'ATR'
  | 'CUSTOM'

const DEFAULT_CONDITION_ROWS: ConditionRow[] = [{ lhs: '', op: '>', rhs: '' }]

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
  const [evaluationCadence, setEvaluationCadence] = useState<string>('')

  const [run, setRun] = useState<ScreenerRun | null>(null)
  const [runLoading, setRunLoading] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  const [matchedOnly, setMatchedOnly] = useState(true)
  const [showVariables, setShowVariables] = useState(false)

  const [createGroupOpen, setCreateGroupOpen] = useState(false)
  const [createGroupName, setCreateGroupName] = useState('')
  const [createGroupSubmitting, setCreateGroupSubmitting] = useState(false)
  const [createGroupError, setCreateGroupError] = useState<string | null>(null)

  const builderDsl = useMemo(
    () => buildDslFromRows(conditionJoin, conditionRows),
    [conditionJoin, conditionRows],
  )

  const variableKindOf = (v: AlertVariableDef): VariableKind => {
    if (v.kind) return v.kind as VariableKind
    return 'DSL'
  }

  const varParams = (v: AlertVariableDef): Record<string, any> => {
    return (v.params ?? {}) as Record<string, any>
  }

  const updateVar = (idx: number, next: AlertVariableDef) => {
    setVariables((prev) => prev.map((v, i) => (i === idx ? next : v)))
  }

  const setVariableKind = (idx: number, kind: VariableKind) => {
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
          kind === 'STDDEV' ||
          kind === 'MAX' ||
          kind === 'MIN' ||
          kind === 'AVG' ||
          kind === 'SUM'
        ) {
          return { name, kind, params: { source: 'close', length: 14, timeframe: '1d' } }
        }
        if (kind === 'RET') return { name, kind: 'RET', params: { source: 'close', timeframe: '1d' } }
        if (kind === 'ATR') return { name, kind: 'ATR', params: { length: 14, timeframe: '1d' } }
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
    enabled: variables.some(
      (v) => (v.kind || '').toString().toUpperCase() === 'CUSTOM',
    ),
  })

  const operandOptions = useMemo(() => {
    const vars = variables
      .map((v) => (v.name || '').trim())
      .filter((x) => x.length > 0)
    return Array.from(new Set([...vars, ...ALERT_V3_METRICS]))
  }, [variables])

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

  const handleAddVariable = () => {
    setVariables((current) => [...current, { name: '', dsl: '' }])
  }

  const handleRun = async () => {
    const groupIds = selectedGroups.map((g) => g.id)
    const dsl = conditionTab === 0 ? builderDsl.trim() : conditionDsl.trim()
    if (!dsl) {
      setRunError('Condition is empty.')
      return
    }
    if (!includeHoldings && groupIds.length === 0) {
      setRunError('Select Holdings and/or at least one group.')
      return
    }

    setRunLoading(true)
    setRunError(null)
    try {
      const res = await runScreener({
        include_holdings: includeHoldings,
        group_ids: groupIds,
        variables: variables
          .map((v) => ({ ...v, name: v.name.trim() }))
          .filter((v) => v.name),
        condition_dsl: dsl,
        evaluation_cadence: evaluationCadence.trim() || null,
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
    const keys = variables.map((v) => v.name).filter(Boolean)
    return keys.map((name) => ({
      field: `var_${name}`,
      headerName: name,
      width: 140,
      valueGetter: (params: any) =>
        ((params.row as ScreenerRow).variables ?? {})[name] ?? null,
    }))
  }, [showVariables, variables])

  const columns: GridColDef[] = useMemo(
    () => [
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
      {
        field: 'rsi_14_1d',
        headerName: 'RSI(14) 1d',
        width: 120,
        renderCell: (params: any) =>
          params.value != null && Number.isFinite(Number(params.value))
            ? Number(params.value).toFixed(2)
            : '—',
      },
      {
        field: 'sma_20_1d',
        headerName: 'SMA(20) 1d',
        width: 120,
        renderCell: (params: any) =>
          params.value != null && Number.isFinite(Number(params.value))
            ? Number(params.value).toFixed(2)
            : '—',
      },
      {
        field: 'sma_50_1d',
        headerName: 'SMA(50) 1d',
        width: 120,
        renderCell: (params: any) =>
          params.value != null && Number.isFinite(Number(params.value))
            ? Number(params.value).toFixed(2)
            : '—',
      },
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
      ...variableColumns,
    ],
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

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
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
                      <MenuItem value="MAX">Max</MenuItem>
                      <MenuItem value="MIN">Min</MenuItem>
                      <MenuItem value="AVG">Avg</MenuItem>
                      <MenuItem value="SUM">Sum</MenuItem>
                      <MenuItem value="RET">Return</MenuItem>
                      <MenuItem value="ATR">ATR</MenuItem>
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
                    {['SMA', 'EMA', 'RSI', 'STDDEV', 'MAX', 'MIN', 'AVG', 'SUM'].includes(
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
              onChange={(_e, v) => setConditionTab(v)}
              sx={{ mb: 1 }}
            >
              <Tab label="Builder" />
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
                          prev.map((row, i) => (i === idx ? { ...row, lhs: v } : row)),
                        )
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="LHS"
                          size="small"
                          sx={{ flex: 1, minWidth: 240 }}
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
                          cur.map((row, i) => (i === idx ? { ...row, op: next } : row)),
                        )
                      }}
                      sx={{ width: 180 }}
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
                          prev.map((row, i) => (i === idx ? { ...row, rhs: v } : row)),
                        )
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="RHS"
                          size="small"
                          sx={{ flex: 1, minWidth: 240 }}
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
                      setConditionRows((cur) => [...cur, { lhs: '', op: '>', rhs: '' }])
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
              <TextField
                label="DSL expression"
                value={conditionDsl}
                onChange={(e) => setConditionDsl(e.target.value)}
                multiline
                minRows={4}
                fullWidth
                helperText="Use the same DSL as Alerts V3 (variables, metrics, indicators, events)."
              />
            )}
          </Box>

          <Stack direction="row" spacing={2} alignItems="center">
            <Button variant="contained" onClick={handleRun} disabled={runLoading}>
              {runLoading ? 'Running…' : 'Run screener'}
            </Button>
            {run && (
              <Typography variant="body2" color="text.secondary">
                Run #{run.id} — {run.status} — {run.matched_symbols}/
                {run.total_symbols} matched — missing {run.missing_symbols}
              </Typography>
            )}
            {runError && (
              <Typography variant="body2" color="error">
                {runError}
              </Typography>
            )}
          </Stack>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
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
          <Button variant="text" onClick={() => navigate('/groups')}>
            Manage groups
          </Button>
        </Stack>
        <Box sx={{ height: 560, width: '100%' }}>
          <DataGrid
            rows={gridRows}
            columns={columns}
            loading={runLoading || (run?.status === 'RUNNING')}
            disableRowSelectionOnClick
            initialState={{
              pagination: { paginationModel: { pageSize: 25 } },
            }}
            pageSizeOptions={[25, 50, 100]}
            localeText={{
              noRowsLabel: run ? 'No rows.' : 'Run a screener to see results.',
            }}
          />
        </Box>
      </Paper>

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
    </Box>
  )
}
