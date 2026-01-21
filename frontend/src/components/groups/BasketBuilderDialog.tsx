import DeleteIcon from '@mui/icons-material/Delete'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import AddIcon from '@mui/icons-material/Add'
import LockIcon from '@mui/icons-material/Lock'
import LockOpenIcon from '@mui/icons-material/LockOpen'
import IconButton from '@mui/material/IconButton'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Tooltip from '@mui/material/Tooltip'
import Alert from '@mui/material/Alert'
import Checkbox from '@mui/material/Checkbox'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import { useEffect, useMemo, useState } from 'react'

import { useMarketQuotes } from '../../hooks/useMarketQuotes'
import { downloadCsv } from '../../utils/csv'
import {
  bulkAddGroupMembers,
  deleteGroupMember,
  fetchGroup,
  freezeBasket,
  updateBasketConfig,
  updateGroupMember,
  type GroupDetail,
  type GroupMember,
} from '../../services/groups'
import { SymbolQuickAdd } from './SymbolQuickAdd'
import type { ParsedSymbol } from './symbolParsing'
import {
  clearUnlocked,
  computeWeightModeAllocation,
  equalizeUnlocked,
  normalizeUnlocked,
} from '../../groups/allocation/engine'
import type { AllocationRowDraft } from '../../groups/allocation/types'

export type BasketBuilderDialogProps = {
  open: boolean
  groupId: number
  group: GroupDetail
  onClose: () => void
  onGroupChange: (next: GroupDetail) => void
}

function toKey(exchange: string | null | undefined, symbol: string): string {
  const exch = (exchange || 'NSE').trim().toUpperCase() || 'NSE'
  const sym = (symbol || '').trim().toUpperCase()
  return `${exch}:${sym}`
}

function parseFunds(text: string): number | null {
  const raw = text.trim().replace(/,/g, '')
  if (!raw) return null
  const n = Number(raw)
  if (!Number.isFinite(n)) return null
  return n
}

export function BasketBuilderDialog({
  open,
  groupId,
  group,
  onClose,
  onGroupChange,
}: BasketBuilderDialogProps) {
  const [defaultExchange, setDefaultExchange] = useState<'NSE' | 'BSE'>('NSE')
  const [fundsText, setFundsText] = useState('')
  const [allocationMode, setAllocationMode] = useState<'WEIGHT'>('WEIGHT')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const [draftWeights, setDraftWeights] = useState<Record<number, number>>({})
  const [draftLocks, setDraftLocks] = useState<Record<number, boolean>>({})
  const [weightsTouched, setWeightsTouched] = useState(false)

  useEffect(() => {
    if (!open) return
    setFundsText(
      group.funds != null && Number.isFinite(Number(group.funds))
        ? String(group.funds)
        : '',
    )
    setAllocationMode(
      (group.allocation_mode || 'WEIGHT').toUpperCase() === 'WEIGHT' ? 'WEIGHT' : 'WEIGHT',
    )
    const w: Record<number, number> = {}
    const l: Record<number, boolean> = {}
    for (const m of group.members ?? []) {
      w[m.id] =
        m.target_weight != null && Number.isFinite(Number(m.target_weight))
          ? Math.round(Number(m.target_weight) * 10000) / 100
          : 0
      l[m.id] = Boolean(m.weight_locked)
    }
    setDraftWeights(w)
    setDraftLocks(l)
    setWeightsTouched(false)
    setError(null)
    setInfo(null)
  }, [group.allocation_mode, group.funds, group.members, open])

  const quoteItems = useMemo(() => {
    return (group.members ?? []).map((m) => ({
      symbol: m.symbol,
      exchange: m.exchange ?? 'NSE',
    }))
  }, [group.members])

  const { quotesByKey, loading: quotesLoading, error: quotesError } =
    useMarketQuotes(quoteItems)

  const allocationRows = useMemo((): AllocationRowDraft[] => {
    return (group.members ?? []).map((m) => ({
      id: String(m.id),
      symbol: m.symbol,
      exchange: m.exchange ?? 'NSE',
      weightPct: draftWeights[m.id] ?? 0,
      locked: draftLocks[m.id] ?? false,
    }))
  }, [draftLocks, draftWeights, group.members])

  // Default behavior: if the basket has no weights yet, treat it as equal-weight
  // and keep it equalized as new symbols are added (until the user edits).
  useEffect(() => {
    if (!open) return
    if (weightsTouched) return
    if (!(group.members?.length ?? 0)) return

    const anyExplicit = (group.members ?? []).some(
      (m) => (m.target_weight ?? 0) > 0,
    )
    const draftSum = allocationRows.reduce((s, r) => s + (Number.isFinite(r.weightPct) ? r.weightPct : 0), 0)
    if (anyExplicit && draftSum > 0.01) return

    const next = equalizeUnlocked(allocationRows)
    const nextById = new Map(next.map((r) => [r.id, r.weightPct] as const))
    const same = allocationRows.every((r) => {
      const n = nextById.get(r.id) ?? 0
      return Math.abs((r.weightPct ?? 0) - n) < 1e-6
    })
    if (same) return

    const nextWeights: Record<number, number> = {}
    for (const r of next) {
      const id = Number(r.id)
      if (!Number.isFinite(id)) continue
      nextWeights[id] = r.weightPct
    }
    setDraftWeights(nextWeights)
  }, [allocationRows, group.members, open, weightsTouched])

  const pricesByRowId = useMemo(() => {
    const map: Record<string, number | null | undefined> = {}
    for (const m of group.members ?? []) {
      const k = toKey(m.exchange, m.symbol)
      map[String(m.id)] = quotesByKey[k]?.ltp ?? null
    }
    return map
  }, [group.members, quotesByKey])

  const funds = parseFunds(fundsText)

  const allocation = useMemo(() => {
    return computeWeightModeAllocation({
      funds: funds ?? 0,
      rows: allocationRows,
      pricesByRowId,
      requireWeightsSumTo100: true,
      minQtyPerRow: 1,
    })
  }, [allocationRows, funds, pricesByRowId])

  const allocationByMemberId = useMemo(() => {
    const out = new Map<number, (typeof allocation.rows)[number]>()
    for (const r of allocation.rows) {
      const id = Number(r.id)
      if (!Number.isFinite(id)) continue
      out.set(id, r)
    }
    return out
  }, [allocation.rows])

  const additionalFundsRequired = allocation.totals.additionalFundsRequired ?? 0
  const displayRemaining =
    additionalFundsRequired > 0.01 ? -additionalFundsRequired : allocation.totals.remaining
  const minFundsRequired = allocation.totals.minFundsRequired ?? null

  const blockingIssues = useMemo(() => {
    const block = new Set(['funds_invalid', 'locked_over_100', 'weights_not_100', 'weight_invalid'])
    return allocation.issues.filter((i) => block.has(i.code))
  }, [allocation.issues])

  const handleExportCsv = () => {
    const now = new Date()
    const stamp = now.toISOString().slice(0, 19).replace(/[:T]/g, '-')
    const safeName = (group.name || `basket_${groupId}`).replace(/[^a-z0-9_-]+/gi, '_')

    const outlierMsg = allocation.issues.find((i) => i.code === 'allocation_outliers')?.message ?? ''
    const totals = allocation.totals

    const rows = (group.members ?? []).map((m) => {
      const allocRow = allocationByMemberId.get(m.id)
      const live = quotesByKey[toKey(m.exchange, m.symbol)]?.ltp ?? null
      const frozen = m.frozen_price ?? null
      const deltaPct =
        live != null && frozen != null && Number(frozen) > 0
          ? ((Number(live) - Number(frozen)) / Number(frozen)) * 100
          : null
      return {
        group: group.name,
        kind: 'BASKET',
        funds_available: totals.funds,
        funds_required_min: totals.minFundsRequired ?? '',
        shortfall: totals.additionalFundsRequired ?? '',
        planned_cost: totals.totalCost,
        remaining: displayRemaining,
        weights_sum_pct: totals.weightSumPct,
        outliers: outlierMsg,
        symbol: m.symbol,
        exchange: m.exchange ?? 'NSE',
        weight_pct: allocRow?.weightPct ?? '',
        locked: draftLocks[m.id] ?? false,
        live_price: live != null ? Number(live) : '',
        frozen_price: frozen != null ? Number(frozen) : '',
        delta_pct: deltaPct != null && Number.isFinite(deltaPct) ? deltaPct : '',
        planned_qty: allocRow?.plannedQty ?? '',
        planned_cost_row: allocRow?.plannedCost ?? '',
        actual_pct: allocRow?.actualPct ?? '',
        drift_pct: allocRow?.driftPct ?? '',
      }
    })

    downloadCsv(`${safeName}_${stamp}.csv`, rows)
  }

  const setDraftFromRows = (rows: AllocationRowDraft[]) => {
    const next: Record<number, number> = {}
    for (const r of rows) {
      const id = Number(r.id)
      if (!Number.isFinite(id)) continue
      next[id] = r.weightPct
    }
    setDraftWeights(next)
    setWeightsTouched(true)
  }

  const refreshGroup = async () => {
    const refreshed = await fetchGroup(groupId)
    onGroupChange(refreshed)
  }

  const handleAddSymbols = async (items: ParsedSymbol[]) => {
    if (!items.length) return
    const existing = new Set((group.members ?? []).map((m) => toKey(m.exchange, m.symbol)))
    const dedup = new Map<string, { symbol: string; exchange: string }>()
    for (const it of items) {
      const sym = it.symbol.trim().toUpperCase()
      const exch = (it.exchange || defaultExchange).trim().toUpperCase()
      const key = `${exch}:${sym}`
      if (!sym) continue
      if (existing.has(key)) continue
      dedup.set(key, { symbol: sym, exchange: exch })
    }
    const payload = Array.from(dedup.values())
    if (!payload.length) {
      setInfo('All symbols already exist in this basket.')
      return
    }
    try {
      setBusy(true)
      setError(null)
      setInfo(null)
      await bulkAddGroupMembers(
        groupId,
        payload.map((p) => ({ symbol: p.symbol, exchange: p.exchange })),
      )
      await refreshGroup()
      setInfo(`Added ${payload.length} symbols.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add symbols')
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async (member: GroupMember) => {
    const ok = window.confirm(`Remove ${member.symbol} from this basket?`)
    if (!ok) return
    try {
      setBusy(true)
      setError(null)
      setInfo(null)
      await deleteGroupMember(groupId, member.id)
      await refreshGroup()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member')
    } finally {
      setBusy(false)
    }
  }

  const handleSave = async () => {
    const n = parseFunds(fundsText)
    if (n == null || !(n > 0)) {
      setError('Enter a valid Funds value.')
      return
    }
    if (blockingIssues.length) {
      setError(blockingIssues[0]?.message ?? 'Fix validation errors before saving.')
      return
    }

    try {
      setBusy(true)
      setError(null)
      setInfo(null)

      await updateBasketConfig(groupId, { funds: n, allocation_mode: allocationMode })

      // Persist member weights + locks (best-effort minimal updates).
      const updates: Array<Promise<unknown>> = []
      for (const m of group.members ?? []) {
        const nextPct = draftWeights[m.id] ?? 0
        const nextTarget = nextPct / 100
        const prevTarget = m.target_weight ?? 0
        const nextLock = draftLocks[m.id] ?? false
        const prevLock = Boolean(m.weight_locked)

        const needWeight = Math.abs(Number(prevTarget) * 100 - nextPct) > 0.01
        const needLock = nextLock !== prevLock
        if (!needWeight && !needLock) continue

        updates.push(
          updateGroupMember(groupId, m.id, {
            target_weight: nextTarget,
            weight_locked: nextLock,
          }),
        )
      }
      if (updates.length) await Promise.all(updates)

      await refreshGroup()
      setInfo('Saved basket.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save basket')
    } finally {
      setBusy(false)
    }
  }

  const handleFreeze = async () => {
    try {
      setBusy(true)
      setError(null)
      setInfo(null)
      const updated = await freezeBasket(groupId)
      onGroupChange(updated)
      setInfo('Frozen prices captured.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to freeze prices')
    } finally {
      setBusy(false)
    }
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
        field: 'weightPct',
        headerName: 'Weight %',
        width: 120,
        sortable: false,
        renderCell: (params: GridRenderCellParams<GroupMember>) => {
          const memberId = params.row.id
          const value = draftWeights[memberId] ?? 0
          return (
            <TextField
              size="small"
              value={String(value)}
              onChange={(e) => {
                const raw = e.target.value
                const n = Number(raw)
                setWeightsTouched(true)
                setDraftWeights((prev) => ({
                  ...prev,
                  [memberId]: Number.isFinite(n) ? n : 0,
                }))
              }}
              inputProps={{ inputMode: 'decimal' }}
              sx={{ width: 100 }}
            />
          )
        },
      },
      {
        field: 'weight_locked',
        headerName: 'Lock',
        width: 90,
        sortable: false,
        renderCell: (params: GridRenderCellParams<GroupMember>) => {
          const memberId = params.row.id
          const locked = draftLocks[memberId] ?? false
          return (
            <Checkbox
              checked={locked}
              icon={<LockOpenIcon fontSize="small" />}
              checkedIcon={<LockIcon fontSize="small" />}
              onChange={(e) =>
                setDraftLocks((prev) => ({ ...prev, [memberId]: e.target.checked }))
              }
            />
          )
        },
      },
      {
        field: 'ltp',
        headerName: 'Live',
        width: 110,
        valueGetter: (_v, row) => {
          const q = quotesByKey[toKey(row.exchange, row.symbol)]
          return q?.ltp ?? null
        },
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
        field: 'delta',
        headerName: 'Δ',
        width: 110,
        valueGetter: (_v, row) => {
          const live = quotesByKey[toKey(row.exchange, row.symbol)]?.ltp ?? null
          const frozen = row.frozen_price ?? null
          if (live == null || frozen == null || frozen <= 0) return null
          return ((live - frozen) / frozen) * 100
        },
        valueFormatter: (v) =>
          v != null && Number.isFinite(Number(v)) ? `${Number(v).toFixed(2)}%` : '—',
      },
      {
        field: 'plannedQty',
        headerName: 'Qty',
        width: 90,
        valueGetter: (_v, row) => {
          return allocationByMemberId.get(row.id)?.plannedQty ?? 0
        },
      },
      {
        field: 'plannedCost',
        headerName: 'Cost',
        width: 120,
        valueGetter: (_v, row) => {
          return allocationByMemberId.get(row.id)?.plannedCost ?? 0
        },
        valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 140,
        sortable: false,
        filterable: false,
        renderCell: (params: GridRenderCellParams<GroupMember>) => (
          <Button
            size="small"
            variant="outlined"
            color="error"
            startIcon={<DeleteIcon />}
            disabled={busy}
            onClick={() => void handleRemove(params.row)}
          >
            Remove
          </Button>
        ),
      },
    ]
    return cols
  }, [allocationByMemberId, busy, draftLocks, draftWeights, group.members, quotesByKey])

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg">
      <DialogTitle>Basket builder (Weight mode)</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          {info && <Alert severity="info">{info}</Alert>}
          {quotesError && <Alert severity="warning">{quotesError}</Alert>}

          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={1}
            alignItems={{ xs: 'stretch', md: 'flex-start' }}
          >
            <TextField
              label="Funds (INR)"
              size="small"
              value={fundsText}
              onChange={(e) => setFundsText(e.target.value)}
              sx={{ width: { xs: '100%', md: 220 } }}
              disabled={busy}
            />
            <Stack direction="row" spacing={0.5} alignItems="center">
              <TextField
                label="Mode"
                size="small"
                select
                value={allocationMode}
                onChange={() => setAllocationMode('WEIGHT')}
                sx={{ width: { xs: '100%', md: 220 } }}
                disabled
              >
                <MenuItem value="WEIGHT">Weight</MenuItem>
              </TextField>
              <Tooltip title="Weight mode is currently supported. Amount/Qty modes will be added later.">
                <span>
                  <IconButton size="small" disabled={busy}>
                    <HelpOutlineIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
            <Chip
              label={
                group.frozen_at
                  ? `Frozen: ${new Date(group.frozen_at).toLocaleString()}`
                  : 'Not frozen'
              }
              variant="outlined"
              sx={{ mt: { xs: 0, md: 0.5 } }}
            />
          </Stack>

          <SymbolQuickAdd
            disabled={busy}
            defaultExchange={defaultExchange}
            onDefaultExchangeChange={setDefaultExchange}
            onAddSymbols={(items) => void handleAddSymbols(items)}
          />

          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Button
              size="small"
              variant="outlined"
              disabled={busy || !(group.members?.length ?? 0)}
              onClick={() => setDraftFromRows(equalizeUnlocked(allocationRows))}
            >
              Equalize
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={busy || !(group.members?.length ?? 0)}
              onClick={() => setDraftFromRows(normalizeUnlocked(allocationRows))}
            >
              Normalize unlocked
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={busy || !(group.members?.length ?? 0)}
              onClick={() => setDraftFromRows(clearUnlocked(allocationRows))}
            >
              Clear unlocked
            </Button>
            <Divider orientation="vertical" flexItem />
            <Button
              size="small"
              variant="outlined"
              disabled={busy || !(group.members?.length ?? 0)}
              onClick={() => void handleFreeze()}
            >
              Freeze prices
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<FileDownloadIcon />}
              disabled={busy || !(group.members?.length ?? 0)}
              onClick={handleExportCsv}
            >
              Export CSV
            </Button>
            <Typography variant="caption" color="text.secondary">
              Quotes refresh every ~5m during market hours.
            </Typography>
          </Stack>

          <Paper variant="outlined" sx={{ p: 1.25 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center">
              <Typography variant="body2">
                Funds available: {allocation.totals.funds.toFixed(2)}
              </Typography>
              <Typography variant="body2">
                Funds required (min): {minFundsRequired != null ? minFundsRequired.toFixed(2) : '-'}
              </Typography>
              <Typography variant="body2">
                Weights sum: {allocation.totals.weightSumPct.toFixed(2)}%
              </Typography>
              <Typography variant="body2">
                Planned cost (live): {allocation.totals.totalCost.toFixed(2)}
              </Typography>
              <Typography
                variant="body2"
                sx={{ color: displayRemaining < -0.01 ? 'error.main' : 'text.primary' }}
              >
                Remaining: {displayRemaining.toFixed(2)}
              </Typography>
              <div style={{ flexGrow: 1 }} />
              {blockingIssues.length ? (
                <Alert severity="warning" sx={{ py: 0, px: 1 }}>
                  {blockingIssues[0]?.message}
                </Alert>
              ) : null}
            </Stack>
            {additionalFundsRequired > 0.01 ? (
              <Alert severity="error" sx={{ mt: 1 }}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <span>
                    Funds required: {minFundsRequired != null ? minFundsRequired.toFixed(2) : '-'}{' '}
                    (available: {allocation.totals.funds.toFixed(2)}). Shortfall: {additionalFundsRequired.toFixed(2)}.
                  </span>
                  <Tooltip title="Add shortfall to Funds (INR)">
                    <span>
                      <IconButton
                        size="small"
                        disabled={busy}
                        onClick={() => {
                          const current = parseFunds(fundsText) ?? 0
                          const next = current + additionalFundsRequired
                          setFundsText(next.toFixed(2))
                        }}
                      >
                        <AddIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </Stack>
              </Alert>
            ) : null}
            {additionalFundsRequired <= 0.01 &&
            Math.abs(allocation.totals.weightSumPct - 100) <= 0.05 &&
            allocation.issues.some((i) => i.code === 'allocation_outliers') ? (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {allocation.issues.find((i) => i.code === 'allocation_outliers')?.message}
              </Alert>
            ) : null}
          </Paper>

          <div style={{ height: 520, width: '100%' }}>
            <DataGrid
              rows={group.members ?? []}
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
        <Button
          variant="contained"
          onClick={() => void handleSave()}
          disabled={busy || blockingIssues.length > 0}
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  )
}
