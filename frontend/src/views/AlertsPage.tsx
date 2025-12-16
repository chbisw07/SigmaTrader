import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import { useEffect, useMemo, useState } from 'react'

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
import {
  listIndicatorRules,
  updateIndicatorRule,
  deleteIndicatorRule,
  type IndicatorRule,
  type IndicatorRuleUpdate,
  type TriggerMode,
} from '../services/indicatorAlerts'
import { listStrategyTemplates, type Strategy } from '../services/strategies'
import {
  fetchHoldingsCorrelation,
  type HoldingsCorrelationResult,
} from '../services/analytics'

type RuleRow = IndicatorRule & {
  id: number
  strategy_name?: string | null
}

export function AlertsPage() {
  const [tab, setTab] = useState(0)
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
        <Tab label="Legacy" />
      </Tabs>
      {tab === 0 && <AlertsV3Tab />}
      {tab === 1 && <IndicatorsV3Tab />}
      {tab === 2 && <EventsV3Tab />}
      {tab === 3 && <LegacyIndicatorAlertsTab />}
    </Box>
  )
}

function AlertsV3Tab() {
  const [rows, setRows] = useState<AlertDefinition[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<AlertDefinition | null>(null)

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

  const formatIstDateTime = (value: unknown): string => {
    if (!value) return '—'
    const raw = new Date(value as string)
    if (Number.isNaN(raw.getTime())) return '—'
    const istOffsetMs = 5.5 * 60 * 60 * 1000
    const ist = new Date(raw.getTime() + istOffsetMs)
    return ist.toLocaleString()
  }

  const columns: GridColDef[] = [
    { field: 'name', headerName: 'Name', flex: 1, minWidth: 220 },
    {
      field: 'target',
      headerName: 'Target',
      width: 220,
      valueGetter: (_v, row) => {
        if (row.target_kind === 'HOLDINGS') return 'Holdings (Zerodha)'
        if (row.target_kind === 'GROUP') return `Group: ${row.target_ref}`
        return `${row.target_ref} / ${(row.exchange ?? 'NSE').toString()}`
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
        Indicator-first alerts over universes. These alerts emit events only (no auto trade execution).
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
        onClose={() => setEditorOpen(false)}
        onSaved={() => void refresh()}
      />
    </Box>
  )
}

type AlertV3EditorDialogProps = {
  open: boolean
  alert: AlertDefinition | null
  onClose: () => void
  onSaved: () => void
}

function AlertV3EditorDialog({
  open,
  alert,
  onClose,
  onSaved,
}: AlertV3EditorDialogProps) {
  const [name, setName] = useState('')
  const [targetKind, setTargetKind] = useState<'SYMBOL' | 'HOLDINGS' | 'GROUP'>(
    'HOLDINGS',
  )
  const [targetRef, setTargetRef] = useState('ZERODHA')
  const [exchange, setExchange] = useState('NSE')
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

  useEffect(() => {
    if (!open) return
    setError(null)
    if (!alert) {
      setName('')
      setTargetKind('HOLDINGS')
      setTargetRef('ZERODHA')
      setExchange('NSE')
      setEvaluationCadence('')
      setVariables([])
      setConditionDsl('')
      setTriggerMode('ONCE_PER_BAR')
      setThrottleSeconds('')
      setOnlyMarketHours(false)
      setExpiresAt('')
      setEnabled(true)
      return
    }
    setName(alert.name)
    setTargetKind(alert.target_kind as any)
    setTargetRef(alert.target_ref)
    setExchange((alert.exchange ?? 'NSE').toString())
    setEvaluationCadence(alert.evaluation_cadence ?? '')
    setVariables(alert.variables ?? [])
    setConditionDsl(alert.condition_dsl)
    setTriggerMode(alert.trigger_mode)
    setThrottleSeconds(alert.throttle_seconds != null ? String(alert.throttle_seconds) : '')
    setOnlyMarketHours(alert.only_market_hours)
    setExpiresAt(alert.expires_at ?? '')
    setEnabled(alert.enabled)
  }, [open, alert])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const payloadBase: AlertDefinitionCreate = {
        name: name.trim() || 'Untitled alert',
        target_kind: targetKind,
        target_ref:
          targetKind === 'HOLDINGS'
            ? 'ZERODHA'
            : targetKind === 'SYMBOL'
              ? targetRef.trim().toUpperCase()
              : targetRef,
        exchange: targetKind === 'SYMBOL' ? exchange : null,
        evaluation_cadence: evaluationCadence.trim() || null,
        variables,
        condition_dsl: conditionDsl.trim(),
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
    setVariables((prev) => prev.map((v, i) => (i === idx ? next : v)))
  }

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>{alert ? 'Edit alert' : 'Create alert'}</DialogTitle>
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
            label="Target kind"
            select
            size="small"
            value={targetKind}
            onChange={(e) => {
              const v = e.target.value as any
              setTargetKind(v)
              if (v === 'HOLDINGS') {
                setTargetRef('ZERODHA')
              }
            }}
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="HOLDINGS">Holdings (Zerodha)</MenuItem>
            <MenuItem value="GROUP">Group</MenuItem>
            <MenuItem value="SYMBOL">Single symbol</MenuItem>
          </TextField>
          {targetKind === 'SYMBOL' && (
            <>
              <TextField
                label="Symbol"
                size="small"
                value={targetRef}
                onChange={(e) => setTargetRef(e.target.value)}
                sx={{ minWidth: 220 }}
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
            <TextField
              label="Group ID"
              size="small"
              value={targetRef}
              onChange={(e) => setTargetRef(e.target.value)}
              helperText="Use numeric group id (for now)."
              sx={{ minWidth: 220 }}
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
        </Box>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Variables (optional)
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Provide readable aliases like <code>RSI_1H_14</code> = <code>RSI(close, 14, &quot;1h&quot;)</code>.
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 2 }}>
          {variables.map((v, idx) => (
            <Box key={idx} sx={{ display: 'flex', gap: 1 }}>
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
                label="DSL"
                size="small"
                value={v.dsl ?? ''}
                onChange={(e) =>
                  updateVar(idx, { ...v, dsl: e.target.value })
                }
                fullWidth
              />
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

        <TextField
          label="Condition DSL"
          size="small"
          value={conditionDsl}
          onChange={(e) => setConditionDsl(e.target.value)}
          multiline
          minRows={4}
          fullWidth
          sx={{ mb: 2 }}
          helperText='Example: RSI_1H_14 < 30 AND TODAY_PNL_PCT > 5'
        />

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
      <DialogTitle>{indicator ? 'Edit custom indicator' : 'Create custom indicator'}</DialogTitle>
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
    </Dialog>
  )
}

function EventsV3Tab() {
  const [rows, setRows] = useState<AlertEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    if (!value) return '—'
    const raw = new Date(value as string)
    if (Number.isNaN(raw.getTime())) return '—'
    const istOffsetMs = 5.5 * 60 * 60 * 1000
    const ist = new Date(raw.getTime() + istOffsetMs)
    return ist.toLocaleString()
  }

  const columns: GridColDef[] = [
    { field: 'triggered_at', headerName: 'Triggered at', width: 190, valueFormatter: (v) => formatIstDateTime(v) },
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'exchange', headerName: 'Exch', width: 90, valueFormatter: (v) => (v ? String(v) : '—') },
    { field: 'alert_definition_id', headerName: 'Alert ID', width: 100 },
    { field: 'reason', headerName: 'Reason', flex: 1, minWidth: 320, valueFormatter: (v) => v ?? '—' },
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
    </Box>
  )
}

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
    if (!value) return '—'
    const raw = new Date(value as string)
    if (Number.isNaN(raw.getTime())) return '—'
    // Treat stored timestamps as UTC and convert to IST (UTC+5:30) so that
    // display matches the user's local trading timezone.
    const istOffsetMs = 5.5 * 60 * 60 * 1000
    const ist = new Date(raw.getTime() + istOffsetMs)
    return ist.toLocaleString()
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
