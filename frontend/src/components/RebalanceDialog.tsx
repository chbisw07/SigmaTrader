import AutorenewIcon from '@mui/icons-material/Autorenew'
import HistoryIcon from '@mui/icons-material/History'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
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
  getRebalanceRun,
  listRebalanceRuns,
  previewRebalance,
  type RebalancePreviewResult,
  type RebalanceRun,
  type RebalanceTargetKind,
} from '../services/rebalance'

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
  budgetPct: string
  budgetAmount: string
  absBandPct: string
  relBandPct: string
  maxTrades: string
  minTradeValue: string
  mode: 'MANUAL' | 'AUTO'
  executionTarget: 'LIVE' | 'PAPER'
  orderType: 'MARKET' | 'LIMIT'
  product: 'CNC' | 'MIS'
  idempotencyKey: string
}

const DEFAULT_REBALANCE: RebalanceDraft = {
  brokerName: 'zerodha',
  budgetPct: '10',
  budgetAmount: '',
  absBandPct: '2',
  relBandPct: '15',
  maxTrades: '10',
  minTradeValue: '2000',
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
  const raw = new Date(value as string)
  if (Number.isNaN(raw.getTime())) return '—'
  const istOffsetMs = 5.5 * 60 * 60 * 1000
  const ist = new Date(raw.getTime() + istOffsetMs)
  return ist.toLocaleString('en-IN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
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

export type RebalanceDialogProps = {
  open: boolean
  onClose: () => void
  title?: string
  targetKind: RebalanceTargetKind
  groupId?: number | null
  brokerName: 'zerodha' | 'angelone'
  brokerLocked?: boolean
}

export function RebalanceDialog({
  open,
  onClose,
  title,
  targetKind,
  groupId,
  brokerName,
  brokerLocked,
}: RebalanceDialogProps) {
  const historyEnabled = targetKind === 'GROUP' && groupId != null
  const [tab, setTab] = useState<'preview' | 'history'>('preview')
  const [helpOpen, setHelpOpen] = useState(false)
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

  useEffect(() => {
    if (!open) return
    setTab('preview')
    setDraft({ ...DEFAULT_REBALANCE, brokerName })
    setError(null)
    setPreviewResults(null)
    setSelectedRun(null)
    setRuns([])
    if (!historyEnabled) return
    void (async () => {
      try {
        const rows = await listRebalanceRuns({ group_id: groupId as number, broker_name: null })
        setRuns(rows)
      } catch {
        // best-effort
      }
    })()
  }, [open, brokerName, historyEnabled, groupId])

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

      const results = await previewRebalance({
        target_kind: targetKind,
        group_id: targetKind === 'GROUP' ? (groupId ?? null) : null,
        broker_name: draft.brokerName,
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

      const results = await executeRebalance({
        target_kind: targetKind,
        group_id: targetKind === 'GROUP' ? (groupId ?? null) : null,
        broker_name: draft.brokerName,
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute rebalance')
    } finally {
      setBusy(false)
    }
  }

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
          onChange={(_e, v) => setTab(v as 'preview' | 'history')}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Preview" value="preview" icon={<AutorenewIcon />} iconPosition="start" />
          {historyEnabled && (
            <Tab label="History" value="history" icon={<HistoryIcon />} iconPosition="start" />
          )}
        </Tabs>

        {tab === 'preview' && (
          <Stack spacing={2} sx={{ mt: 2 }}>
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
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>

      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Rebalance help</DialogTitle>
        <DialogContent dividers>
          <MarkdownLite text={rebalanceHelpText} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Dialog>
  )
}
