import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import Paper from '@mui/material/Paper'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'

import { listTvAlerts, type TvAlert } from '../services/tvAlerts'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

type PayloadRow = { id: string; key: string; value: string }
type TvAlertRow = TvAlert & { strategy_display: string }

const formatDateLocal = (d: Date): string => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const dateRangeToIso = (range: { from: string; to: string }): { fromIso?: string; toIso?: string } => {
  const from = (range.from || '').trim()
  const to = (range.to || '').trim()
  if (!from && !to) return {}
  const out: { fromIso?: string; toIso?: string } = {}
  if (from) out.fromIso = new Date(`${from}T00:00:00`).toISOString()
  if (to) out.toIso = new Date(`${to}T23:59:59.999`).toISOString()
  return out
}

function formatValue(value: unknown): string {
  if (value == null) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function flattenJson(
  value: unknown,
  prefix = '',
  out: Array<{ key: string; value: unknown }> = [],
): Array<{ key: string; value: unknown }> {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      out.push({ key: prefix || '(root)', value: [] })
      return out
    }
    value.forEach((item, idx) => {
      const nextPrefix = prefix ? `${prefix}[${idx}]` : `[${idx}]`
      flattenJson(item, nextPrefix, out)
    })
    return out
  }

  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) {
      out.push({ key: prefix || '(root)', value: {} })
      return out
    }
    for (const [k, v] of entries) {
      const nextPrefix = prefix ? `${prefix}.${k}` : k
      flattenJson(v, nextPrefix, out)
    }
    return out
  }

  out.push({ key: prefix || '(root)', value })
  return out
}

function safeParseJson(text: string): { parsed: unknown | null; error: string | null } {
  try {
    const parsed = JSON.parse(text)
    return { parsed, error: null }
  } catch (err) {
    return { parsed: null, error: err instanceof Error ? err.message : 'Invalid JSON' }
  }
}

function extractStrategyIdFromPayload(raw: string): string | null {
  const { parsed } = safeParseJson(raw || '')
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
  const obj = parsed as Record<string, unknown>

  const signal =
    obj.signal && typeof obj.signal === 'object' && !Array.isArray(obj.signal)
      ? (obj.signal as Record<string, unknown>)
      : null

  const candidates = [
    signal?.strategy_id,
    signal?.strategyId,
    signal?.strategy,
    signal?.strategy_name,
    signal?.strategyName,
    obj.strategy_id,
    obj.strategyId,
    obj.strategy,
    obj.strategy_name,
    obj.strategyName,
  ]
  for (const v of candidates) {
    if (v == null) continue
    const s = String(v).trim()
    if (s) return s
  }
  return null
}

export function TvAlertsPanel({
  embedded = false,
  active = true,
}: {
  embedded?: boolean
  active?: boolean
}) {
  const { displayTimeZone } = useTimeSettings()
  const today = formatDateLocal(new Date())
  const [rows, setRows] = useState<TvAlertRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loadedOnce, setLoadedOnce] = useState(false)
  const [openPayload, setOpenPayload] = useState<TvAlertRow | null>(null)
  const [payloadTab, setPayloadTab] = useState<'table' | 'json'>('table')
  const [showRawJson, setShowRawJson] = useState(false)
  const [payloadRows, setPayloadRows] = useState<PayloadRow[]>([])
  const [payloadJsonPretty, setPayloadJsonPretty] = useState<string>('')
  const [payloadParseError, setPayloadParseError] = useState<string | null>(null)
  const [rangeDraft, setRangeDraft] = useState<{ from: string; to: string }>({
    from: today,
    to: today,
  })
  const [rangeApplied, setRangeApplied] = useState<{ from: string; to: string }>({
    from: today,
    to: today,
  })

  const refresh = async (options: { silent?: boolean } = {}) => {
    const { silent = false } = options
    try {
      if (!silent) setLoading(true)
      const { fromIso, toIso } = dateRangeToIso(rangeApplied)
      const data = await listTvAlerts({
        receivedFrom: fromIso,
        receivedTo: toIso,
      })
      const enriched: TvAlertRow[] = data.map((a) => {
        const rawStrategyId =
          extractStrategyIdFromPayload(a.raw_payload) ??
          (a.strategy_id != null ? String(a.strategy_id) : null)
        return {
          ...a,
          strategy_display: rawStrategyId ?? a.strategy_name ?? '—',
        }
      })
      setRows(enriched)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load TV alerts')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    if (!active) return
    if (loadedOnce) return
    setLoadedOnce(true)
    void refresh()
  }, [active, loadedOnce])

  useEffect(() => {
    if (!active || !loadedOnce) return
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rangeApplied])

  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      void refresh({ silent: true })
    }, 5000)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, rangeApplied])

  useEffect(() => {
    if (!openPayload) return

    setPayloadTab('table')
    setShowRawJson(false)
    const raw = openPayload.raw_payload ?? ''

    const { parsed, error: parseError } = safeParseJson(raw)
    setPayloadParseError(parseError)

    if (parseError || parsed == null) {
      setPayloadRows([{ id: 'raw_payload', key: 'raw_payload', value: raw }])
      setPayloadJsonPretty(raw)
      return
    }

    const flattened = flattenJson(parsed)
    setPayloadRows(
      flattened.map((item) => ({
        id: item.key,
        key: item.key,
        value: formatValue(item.value),
      })),
    )
    setPayloadJsonPretty(JSON.stringify(parsed, null, 2))
  }, [openPayload])

  const columns: GridColDef[] = [
    {
      field: 'received_at',
      headerName: 'Received At',
      width: 190,
      valueFormatter: (value) =>
        typeof value === 'string'
          ? formatInDisplayTimeZone(value, displayTimeZone)
          : '',
    },
    {
      field: 'strategy_display',
      headerName: 'Strategy',
      width: 220,
      valueGetter: (_value, row) => {
        const alert = row as TvAlertRow
        return alert.strategy_display || '—'
      },
    },
    { field: 'symbol', headerName: 'Symbol', width: 200 },
    { field: 'action', headerName: 'Side', width: 80 },
    { field: 'qty', headerName: 'Qty', width: 90, type: 'number' },
    {
      field: 'price',
      headerName: 'Price',
      width: 110,
      type: 'number',
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '—',
    },
    {
      field: 'interval',
      headerName: 'TF',
      width: 90,
      valueFormatter: (value) => (value ? String(value) : '—'),
    },
    {
      field: 'reason',
      headerName: 'Reason',
      flex: 1,
      minWidth: 200,
      valueFormatter: (value) => (value ? String(value) : '—'),
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 120,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const alert = params.row as TvAlertRow
        return (
          <Button
            size="small"
            variant="outlined"
            onClick={() => setOpenPayload(alert)}
          >
            Payload
          </Button>
        )
      },
    },
  ]

  if (!active) return null

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 2,
          mb: embedded ? 1.5 : 2,
          flexWrap: 'wrap',
        }}
      >
        <Box>
          {!embedded && (
            <Typography variant="h4" gutterBottom>
              TV Alerts
            </Typography>
          )}
          <Typography color="text.secondary">
            TradingView webhook alerts ingested by SigmaTrader.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            size="small"
            label="From"
            type="date"
            value={rangeDraft.from}
            onChange={(e) => setRangeDraft((prev) => ({ ...prev, from: e.target.value }))}
            InputLabelProps={{ shrink: true }}
            sx={{ width: 150 }}
          />
          <TextField
            size="small"
            label="To"
            type="date"
            value={rangeDraft.to}
            onChange={(e) => setRangeDraft((prev) => ({ ...prev, to: e.target.value }))}
            InputLabelProps={{ shrink: true }}
            sx={{ width: 150 }}
          />
          <Button
            variant="outlined"
            size="small"
            onClick={() => {
              const a = (rangeDraft.from || '').trim()
              const b = (rangeDraft.to || '').trim()
              if (a && b && a > b) {
                setError('Invalid date range: From must be <= To.')
                return
              }
              if (a && b) {
                const days =
                  Math.floor(
                    (new Date(`${b}T00:00:00`).getTime() -
                      new Date(`${a}T00:00:00`).getTime()) /
                      (24 * 60 * 60 * 1000),
                  ) + 1
                if (days > 15) {
                  setError('Date range too large; max allowed is 15 days.')
                  return
                }
              }
              setError(null)
              setRangeApplied(rangeDraft)
            }}
            disabled={loading}
          >
            Apply
          </Button>
          <Button
            variant="text"
            size="small"
            onClick={() => {
              const t = formatDateLocal(new Date())
              setError(null)
              setRangeDraft({ from: t, to: t })
              setRangeApplied({ from: t, to: t })
            }}
            disabled={loading}
          >
            Today
          </Button>
          <Button
            variant="outlined"
            size="small"
            onClick={() => {
              void refresh()
            }}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading TV alerts...</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Paper
          sx={{
            width: '100%',
            mt: 2,
            height: embedded ? '65vh' : undefined,
          }}
        >
          <DataGrid
            rows={rows}
            columns={columns}
            getRowId={(row) => row.id}
            {...(embedded ? {} : { autoHeight: true })}
            disableRowSelectionOnClick
            density="compact"
            sx={embedded ? { height: '100%' } : undefined}
            initialState={{
              sorting: {
                sortModel: [{ field: 'received_at', sort: 'desc' }],
              },
            }}
          />
        </Paper>
      )}

      <Dialog
        open={openPayload != null}
        onClose={() => setOpenPayload(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>TradingView payload</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Tabs
            value={payloadTab}
            onChange={(_e, v) => setPayloadTab(v as 'table' | 'json')}
            sx={{ mb: 1 }}
          >
            <Tab value="table" label="Table" />
            <Tab value="json" label="JSON" />
          </Tabs>
          <Divider sx={{ mb: 2 }} />
          {payloadTab === 'table' ? (
            <>
              {payloadParseError && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Payload is not valid JSON; showing raw text.
                </Typography>
              )}
              <Paper sx={{ height: 460 }}>
                <DataGrid
                  rows={payloadRows}
                  columns={[
                    { field: 'key', headerName: 'Key', width: 260 },
                    { field: 'value', headerName: 'Value', flex: 1, minWidth: 320 },
                  ]}
                  getRowId={(row) => row.id}
                  disableRowSelectionOnClick
                  density="compact"
                  sx={{ height: '100%' }}
                />
              </Paper>
            </>
          ) : (
            <>
              <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={showRawJson}
                      onChange={(_e, checked) => setShowRawJson(checked)}
                      size="small"
                    />
                  }
                  label={showRawJson ? 'Raw' : 'Formatted'}
                />
              </Box>
              <TextField
                value={
                  showRawJson ? (openPayload?.raw_payload ?? '') : payloadJsonPretty
                }
                fullWidth
                multiline
                minRows={14}
                size="small"
                InputProps={{ readOnly: true }}
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenPayload(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
