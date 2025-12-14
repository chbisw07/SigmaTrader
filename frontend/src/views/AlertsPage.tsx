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
      <Typography variant="h4" gutterBottom>
        Alerts
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Indicator-based alert rules created from Holdings, grouped by symbol and
        strategy.
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
