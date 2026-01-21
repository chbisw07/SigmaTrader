import FileDownloadIcon from '@mui/icons-material/FileDownload'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import IconButton from '@mui/material/IconButton'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Alert from '@mui/material/Alert'
import Tooltip from '@mui/material/Tooltip'
import {
  DataGrid,
  type GridColDef,
} from '@mui/x-data-grid'
import { useMemo, useState } from 'react'

import { useMarketQuotes } from '../../hooks/useMarketQuotes'
import { downloadCsv } from '../../utils/csv'
import {
  buyBasketToPortfolio,
  type BasketBuyResponse,
  type GroupDetail,
  type GroupMember,
} from '../../services/groups'
import {
  computeAmountModeAllocation,
  computeQtyModeAllocation,
  computeWeightModeAllocation,
} from '../../groups/allocation/engine'
import type { AllocationRowDraft } from '../../groups/allocation/types'

export type BuyPreviewDialogProps = {
  open: boolean
  basketGroupId: number
  basket: GroupDetail
  onClose: () => void
  onBought: (res: BasketBuyResponse) => void
}

function toKey(exchange: string | null | undefined, symbol: string): string {
  const exch = (exchange || 'NSE').trim().toUpperCase() || 'NSE'
  const sym = (symbol || '').trim().toUpperCase()
  return `${exch}:${sym}`
}

export function BuyPreviewDialog({
  open,
  basketGroupId,
  basket,
  onClose,
  onBought,
}: BuyPreviewDialogProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [brokerName, setBrokerName] = useState<'zerodha' | 'angelone'>('zerodha')
  const [executionTarget, setExecutionTarget] = useState<'LIVE' | 'PAPER'>('LIVE')
  const [product, setProduct] = useState<'CNC' | 'MIS'>('CNC')

  const quoteItems = useMemo(() => {
    return (basket.members ?? []).map((m) => ({
      symbol: m.symbol,
      exchange: m.exchange ?? 'NSE',
    }))
  }, [basket.members])

  const { quotesByKey, loading: quotesLoading, error: quotesError } =
    useMarketQuotes(quoteItems)

  const allocationMode = useMemo(() => {
    const m = String(basket.allocation_mode || 'WEIGHT').toUpperCase()
    return m === 'AMOUNT' ? 'AMOUNT' : m === 'QTY' ? 'QTY' : 'WEIGHT'
  }, [basket.allocation_mode])

  const allocationRows = useMemo((): AllocationRowDraft[] => {
    return (basket.members ?? []).map((m) => ({
      id: String(m.id),
      symbol: m.symbol,
      exchange: m.exchange ?? 'NSE',
      weightPct:
        allocationMode === 'WEIGHT' &&
        m.target_weight != null &&
        Number.isFinite(Number(m.target_weight))
          ? Number(m.target_weight) * 100
          : undefined,
      amountInr:
        allocationMode === 'AMOUNT' &&
        m.allocation_amount != null &&
        Number.isFinite(Number(m.allocation_amount))
          ? Number(m.allocation_amount)
          : undefined,
      qty:
        allocationMode === 'QTY' &&
        m.allocation_qty != null &&
        Number.isFinite(Number(m.allocation_qty))
          ? Math.max(0, Math.trunc(Number(m.allocation_qty)))
          : undefined,
      locked: false,
    }))
  }, [allocationMode, basket.members])

  const pricesByRowId = useMemo(() => {
    const map: Record<string, number | null | undefined> = {}
    for (const m of basket.members ?? []) {
      map[String(m.id)] = quotesByKey[toKey(m.exchange, m.symbol)]?.ltp ?? null
    }
    return map
  }, [basket.members, quotesByKey])

  const funds = basket.funds != null ? Number(basket.funds) : 0
  const allocation = useMemo(() => {
    const base = { funds, rows: allocationRows, pricesByRowId }
    if (allocationMode === 'AMOUNT') return computeAmountModeAllocation(base)
    if (allocationMode === 'QTY') return computeQtyModeAllocation(base)
    return computeWeightModeAllocation({
      ...base,
      requireWeightsSumTo100: true,
      minQtyPerRow: 1,
    })
  }, [allocationMode, allocationRows, funds, pricesByRowId])

  const rowsById = useMemo(() => {
    const out = new Map<number, (typeof allocation.rows)[number]>()
    for (const r of allocation.rows) {
      const id = Number(r.id)
      if (!Number.isFinite(id)) continue
      out.set(id, r)
    }
    return out
  }, [allocation.rows])

  const canBuy = useMemo(() => {
    if (!basket.members?.length) return false
    if (!(funds > 0)) return false
    if (!basket.frozen_at) return false
    if (allocation.issues.some((i) => i.level === 'error')) return false
    const planned = allocation.rows.filter((r) => r.qty > 0 && !r.issues.some((i) => i.level === 'error'))
    return planned.length > 0
  }, [allocation.issues, allocation.rows, basket.frozen_at, basket.members?.length, funds])

  const additionalFundsRequired = allocation.totals.additionalFundsRequired ?? 0
  const displayRemaining =
    additionalFundsRequired > 0.01 ? -additionalFundsRequired : allocation.totals.remaining
  const minFundsRequired = allocation.totals.minFundsRequired ?? null

  const handleExportCsv = () => {
    const now = new Date()
    const stamp = now.toISOString().slice(0, 19).replace(/[:T]/g, '-')
    const safeName = (basket.name || `basket_${basketGroupId}`).replace(/[^a-z0-9_-]+/gi, '_')

    const outlierMsg = allocation.issues.find((i) => i.code === 'allocation_outliers')?.message ?? ''
    const totals = allocation.totals

    const rows = (basket.members ?? []).map((m) => {
      const allocRow = rowsById.get(m.id)
      const live = quotesByKey[toKey(m.exchange, m.symbol)]?.ltp ?? null
      return {
        basket: basket.name,
        allocation_mode: allocationMode,
        funds_available: totals.funds,
        funds_required_min: totals.minFundsRequired ?? '',
        shortfall: totals.additionalFundsRequired ?? '',
        est_cost: totals.totalCost,
        remaining: displayRemaining,
        weights_sum_pct: totals.weightSumPct,
        outliers: outlierMsg,
        symbol: m.symbol,
        exchange: m.exchange ?? 'NSE',
        weight_pct: allocRow?.weightPct ?? '',
        ltp: live != null ? Number(live) : '',
        frozen_price: m.frozen_price ?? '',
        amount_inr: allocRow?.amountInr ?? '',
        planned_qty: allocRow?.qty ?? '',
        est_cost_row: allocRow?.plannedCost ?? '',
        actual_pct: allocRow?.actualPct ?? '',
        drift_pct: allocRow?.driftPct ?? '',
      }
    })

    downloadCsv(`${safeName}_buy_preview_${stamp}.csv`, rows)
  }

  const columns = useMemo((): GridColDef<GroupMember>[] => {
    const cols: GridColDef<GroupMember>[] = [
      { field: 'symbol', headerName: 'Symbol', width: 140 },
      {
        field: 'exchange',
        headerName: 'Exchange',
        width: 110,
        valueGetter: (_v, row) => row.exchange ?? 'NSE',
      },
      {
        field: 'ltp',
        headerName: 'LTP',
        width: 110,
        valueGetter: (_v, row) => quotesByKey[toKey(row.exchange, row.symbol)]?.ltp ?? null,
        valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
      },
      {
        field: 'frozen_price',
        headerName: 'Frozen',
        width: 110,
        valueGetter: (_v, row) => row.frozen_price ?? null,
        valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
      },
      {
        field: 'weightPct',
        headerName: 'Weight %',
        width: 110,
        valueGetter: (_v, row) => rowsById.get(row.id)?.weightPct ?? 0,
        valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '0.00'),
      },
      {
        field: 'amountInr',
        headerName: 'Amount',
        width: 130,
        valueGetter: (_v, row) => rowsById.get(row.id)?.amountInr ?? 0,
        valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '0.00'),
      },
      {
        field: 'qty',
        headerName: 'Qty',
        width: 120,
        valueGetter: (_v, row) => rowsById.get(row.id)?.qty ?? 0,
      },
      {
        field: 'cost',
        headerName: 'Est cost',
        width: 120,
        valueGetter: (_v, row) => rowsById.get(row.id)?.plannedCost ?? 0,
        valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
      },
    ]
    return cols
  }, [quotesByKey, rowsById])

  const handleBuy = async () => {
    try {
      setBusy(true)
      setError(null)
      const items = allocation.rows
        .filter((r) => r.qty > 0 && !r.issues.some((i) => i.level === 'error'))
        .map((r) => ({
          symbol: r.symbol,
          exchange: r.exchange ?? 'NSE',
          qty: r.qty,
        }))
      if (!items.length) {
        setError('No valid planned orders to create.')
        return
      }
      const res = await buyBasketToPortfolio(basketGroupId, {
        broker_name: brokerName,
        product,
        order_type: 'MARKET',
        execution_target: executionTarget,
        items,
      })
      onBought(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to buy basket')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg">
      <DialogTitle>Buy basket → portfolio (preview)</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          {quotesError && <Alert severity="warning">{quotesError}</Alert>}
          {!basket.frozen_at && (
            <Alert severity="warning">
              Freeze basket prices before buying (required for traceability).
            </Alert>
          )}

          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={1}
            alignItems={{ xs: 'stretch', md: 'flex-start' }}
          >
            <TextField
              label="Broker"
              size="small"
              select
              value={brokerName}
              onChange={(e) =>
                setBrokerName(e.target.value === 'angelone' ? 'angelone' : 'zerodha')
              }
              sx={{ width: { xs: '100%', md: 180 } }}
              disabled={busy}
            >
              <MenuItem value="zerodha">Zerodha</MenuItem>
              <MenuItem value="angelone">AngelOne</MenuItem>
            </TextField>
            <TextField
              label="Execution target"
              size="small"
              select
              value={executionTarget}
              onChange={(e) =>
                setExecutionTarget(e.target.value === 'PAPER' ? 'PAPER' : 'LIVE')
              }
              sx={{ width: { xs: '100%', md: 180 } }}
              disabled={busy}
            >
              <MenuItem value="LIVE">LIVE</MenuItem>
              <MenuItem value="PAPER">PAPER</MenuItem>
            </TextField>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <TextField
                label="Product"
                size="small"
                select
                value={product}
                onChange={(e) => setProduct(e.target.value === 'MIS' ? 'MIS' : 'CNC')}
                sx={{ width: { xs: '100%', md: 180 } }}
                disabled={busy}
              >
                <MenuItem value="CNC">CNC</MenuItem>
                <MenuItem value="MIS">MIS</MenuItem>
              </TextField>
              <Tooltip title="Product is passed to queued orders (CNC/MIS).">
                <span>
                  <IconButton size="small" disabled={busy}>
                    <HelpOutlineIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
            <div style={{ flexGrow: 1 }} />
            <Button
              size="small"
              variant="outlined"
              startIcon={<FileDownloadIcon />}
              disabled={busy || !(basket.members?.length ?? 0)}
              onClick={handleExportCsv}
            >
              Export CSV
            </Button>
            <Typography variant="body2" color="text.secondary">
              Funds available: {Number.isFinite(funds) ? funds.toFixed(2) : '-'} | Funds required (min):{' '}
              {minFundsRequired != null ? minFundsRequired.toFixed(2) : '-'} | Est cost:{' '}
              {allocation.totals.totalCost.toFixed(2)} | Balance:{' '}
              <span style={{ color: displayRemaining < -0.01 ? '#d32f2f' : undefined }}>
                {displayRemaining.toFixed(2)}
              </span>
            </Typography>
          </Stack>

          {additionalFundsRequired > 0.01 ? (
            <Alert severity="error">
              Funds required: {minFundsRequired != null ? minFundsRequired.toFixed(2) : '-'} (available: {funds.toFixed(2)}). Shortfall: {additionalFundsRequired.toFixed(2)}.
            </Alert>
          ) : null}
          {additionalFundsRequired <= 0.01 &&
          Math.abs(allocation.totals.weightSumPct - 100) <= 0.05 &&
          allocation.issues.some((i) => i.code === 'allocation_outliers') ? (
            <Alert severity="warning">
              {allocation.issues.find((i) => i.code === 'allocation_outliers')?.message}
            </Alert>
          ) : null}

          <Paper variant="outlined" sx={{ p: 1.25 }}>
            <Typography variant="caption" color="text.secondary">
              Creates a new Portfolio group + WAITING orders. Executions and avg buy price come from existing order execution/sync (no risk policy changes).
            </Typography>
          </Paper>
          <Typography variant="caption" color="text.secondary">
            Quotes refresh every ~5m during market hours.
          </Typography>

          <div style={{ height: 520, width: '100%' }}>
            <DataGrid
              rows={basket.members ?? []}
              columns={columns}
              getRowId={(row) => row.id}
              disableRowSelectionOnClick
              loading={quotesLoading || busy}
              pageSizeOptions={[10, 25, 50]}
              initialState={{ pagination: { paginationModel: { pageSize: 25, page: 0 } } }}
            />
          </div>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Close
        </Button>
        <Button variant="contained" onClick={() => void handleBuy()} disabled={busy || !canBuy}>
          Create portfolio + orders
        </Button>
      </DialogActions>
    </Dialog>
  )
}
