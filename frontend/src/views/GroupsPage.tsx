import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import PlayListAddIcon from '@mui/icons-material/PlaylistAdd'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import Step from '@mui/material/Step'
import StepLabel from '@mui/material/StepLabel'
import Stepper from '@mui/material/Stepper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Autocomplete from '@mui/material/Autocomplete'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { getPaginatedRowNumber } from '../components/UniverseGrid/getPaginatedRowNumber'
import { createManualOrder } from '../services/orders'
import { fetchHoldings, type Holding } from '../services/positions'
import { searchMarketSymbols, type MarketSymbol } from '../services/marketData'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'
import {
  addGroupMember,
  bulkAddGroupMembers,
  createGroup,
  deleteGroup,
  deleteGroupMember,
  fetchGroup,
  importWatchlistCsv,
  listGroups,
  updateGroup,
  updateGroupMember,
  type Group,
  type GroupDetail,
  type GroupKind,
  type GroupMember,
} from '../services/groups'

type GroupFormState = {
  name: string
  kind: GroupKind
  description: string
}

type BulkAddState = {
  exchange: string
  symbolsText: string
}

type AllocationMode = 'equal' | 'weights'

type AllocationDraft = {
  side: 'BUY' | 'SELL'
  orderType: 'MARKET' | 'LIMIT'
  product: string
  totalAmount: string
  mode: AllocationMode
}

type AllocationPreviewRow = {
  id: string
  symbol: string
  exchange?: string | null
  weightFraction: number
  amount: number
  lastPrice?: number | null
  qty: number
  warning?: string
}

const GROUP_KINDS: Array<{ value: GroupKind; label: string }> = [
  { value: 'WATCHLIST', label: 'Watchlist' },
  { value: 'MODEL_PORTFOLIO', label: 'Basket' },
  { value: 'PORTFOLIO', label: 'Portfolio' },
  { value: 'HOLDINGS_VIEW', label: 'Holdings view' },
]

const DEFAULT_GROUP_FORM: GroupFormState = {
  name: '',
  kind: 'WATCHLIST',
  description: '',
}

const DEFAULT_BULK_ADD: BulkAddState = {
  exchange: 'NSE',
  symbolsText: '',
}

const DEFAULT_ALLOCATION: AllocationDraft = {
  side: 'BUY',
  orderType: 'MARKET',
  product: 'CNC',
  totalAmount: '',
  mode: 'equal',
}

const GROUPS_LEFT_PANEL_WIDTH_STORAGE_KEY = 'st_groups_left_panel_width_v1'
const DEFAULT_LEFT_PANEL_WIDTH = 800

function normalizeLines(text: string): string[] {
  return text
    .split(/[\n,]+/g)
    .map((s) => s.trim())
    .filter(Boolean)
}

function parseCsvLine(line: string): string[] {
  const out: string[] = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"'
        i += 1
      } else {
        inQuotes = !inQuotes
      }
      continue
    }
    if (ch === ',' && !inQuotes) {
      out.push(current)
      current = ''
      continue
    }
    current += ch
  }
  out.push(current)
  return out.map((s) => s.trim())
}

function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const lines = text
    .split(/\r?\n/g)
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
  if (!lines.length) return { headers: [], rows: [] }
  const headers = parseCsvLine(lines[0] ?? '')
  const rows = lines.slice(1).map((l) => parseCsvLine(l))
  return { headers, rows }
}

function dedupeHeaders(headers: string[]): {
  keys: string[]
  labels: Record<string, string>
} {
  const counts = new Map<string, number>()
  const keys: string[] = []
  const labels: Record<string, string> = {}
  headers.forEach((raw) => {
    const base = (raw || '').trim() || 'Column'
    const seen = counts.get(base) ?? 0
    counts.set(base, seen + 1)
    const key = seen === 0 ? base : `${base}__${seen + 1}`
    const label = seen === 0 ? base : `${base} (${seen + 1})`
    keys.push(key)
    labels[key] = label
  })
  return { keys, labels }
}

function disallowedColumnReason(label: string): string | null {
  const s = (label || '').trim()
  if (!s) return 'Empty column.'
  const rules: Array<[RegExp, string]> = [
    [/\b(open|high|low|close|ohlc)\b/i, 'OHLC price fields are not importable.'],
    [/\b(volume|vol)\b/i, 'Volume fields are not importable.'],
    [/\b(price|ltp|last\s*price|bid|ask)\b/i, 'Price fields are not importable.'],
    [/\b(pnl|p&l|p\/l|profit|loss)\b/i, 'P&L fields are not importable.'],
    [/\b(return|ret|change|chg|drawdown|dd)\b/i, 'Performance fields are not importable.'],
    [/\b(rsi|sma|ema|atr|macd|stoch|boll|stddev|vwap|obv)\b/i, 'Indicator fields are not importable.'],
    [/\b(beta|alpha|sharpe|sortino|volatility|iv)\b/i, 'Risk/volatility metrics are not importable.'],
    [/\b(p\s*\/\s*e|p\s*\/\s*b|pe\b|pb\b|eps\b|roe\b|roce\b|ratio)\b/i, 'Fundamental ratio fields are not importable.'],
  ]
  for (const [pat, reason] of rules) {
    if (pat.test(s)) return reason
  }
  return null
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

export function GroupsPage() {
  const { displayTimeZone } = useTimeSettings()
  const navigate = useNavigate()
  const location = useLocation()
  const preferredGroupName = useMemo(() => {
    const raw = new URLSearchParams(location.search).get('group')
    return raw?.trim() ? raw.trim() : null
  }, [location.search])

  const [groups, setGroups] = useState<Group[]>([])
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [selectedGroup, setSelectedGroup] = useState<GroupDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [groupDialogOpen, setGroupDialogOpen] = useState(false)
  const [groupDialogMode, setGroupDialogMode] = useState<'create' | 'edit'>(
    'create',
  )
  const [groupForm, setGroupForm] = useState<GroupFormState>(DEFAULT_GROUP_FORM)
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null)

  const [newMemberSymbol, setNewMemberSymbol] = useState('')
  const [newMemberExchange, setNewMemberExchange] = useState('NSE')
  const [newMemberNotes, setNewMemberNotes] = useState('')
  const [symbolOptions, setSymbolOptions] = useState<MarketSymbol[]>([])
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false)
  const [symbolOptionsError, setSymbolOptionsError] = useState<string | null>(null)

  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkState, setBulkState] = useState<BulkAddState>(DEFAULT_BULK_ADD)

  const [editMemberOpen, setEditMemberOpen] = useState(false)
  const [memberDraft, setMemberDraft] = useState<{
    memberId: number | null
    symbol: string
    exchange?: string | null
    weightPct: string
    refQty: string
    refPrice: string
    notes: string
  }>({
    memberId: null,
    symbol: '',
    exchange: null,
    weightPct: '',
    refQty: '',
    refPrice: '',
    notes: '',
  })

  const [allocateOpen, setAllocateOpen] = useState(false)
  const [allocationDraft, setAllocationDraft] =
    useState<AllocationDraft>(DEFAULT_ALLOCATION)
  const [allocationPreview, setAllocationPreview] = useState<
    AllocationPreviewRow[]
  >([])
  const [allocationError, setAllocationError] = useState<string | null>(null)
  const [allocationBusy, setAllocationBusy] = useState(false)

  // Import watchlist (CSV) wizard state
  type ImportGroupKind = Exclude<GroupKind, 'HOLDINGS_VIEW'>
  const [importOpen, setImportOpen] = useState(false)
  const [importStep, setImportStep] = useState(0)
  const [importFileName, setImportFileName] = useState<string | null>(null)
  const [importHeaders, setImportHeaders] = useState<string[]>([])
  const [importHeaderLabels, setImportHeaderLabels] = useState<
    Record<string, string>
  >({})
  const [importRows, setImportRows] = useState<Array<Record<string, string>>>([])
  const [importPreviewRows, setImportPreviewRows] = useState<
    Array<Record<string, string>>
  >([])
  const [importSymbolColumn, setImportSymbolColumn] = useState<string>('')
  const [importExchangeColumn, setImportExchangeColumn] = useState<string>('')
  const [importDefaultExchange, setImportDefaultExchange] = useState('NSE')
  const [importGroupKind, setImportGroupKind] =
    useState<ImportGroupKind>('WATCHLIST')
  const [importRefQtyColumn, setImportRefQtyColumn] = useState<string>('')
  const [importTargetWeightColumn, setImportTargetWeightColumn] = useState<string>('')
  const [importRefPriceColumn, setImportRefPriceColumn] = useState<string>('')
  const [importStripPrefix, setImportStripPrefix] = useState(true)
  const [importStripSpecial, setImportStripSpecial] = useState(true)
  const [importSelectedColumns, setImportSelectedColumns] = useState<string[]>([])
  const [importGroupName, setImportGroupName] = useState('')
  const [importGroupDescription, setImportGroupDescription] = useState('')
  const [importReplaceIfExists, setImportReplaceIfExists] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<{
    groupId: number
    importedMembers: number
    importedColumns: number
    skippedSymbols: number
    skippedColumns: number
  } | null>(null)

  // Resizable panel state
  const containerRef = useRef<HTMLDivElement>(null)
  const [leftPanelWidth, setLeftPanelWidth] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_LEFT_PANEL_WIDTH
    try {
      const raw = window.localStorage.getItem(GROUPS_LEFT_PANEL_WIDTH_STORAGE_KEY)
      const parsed = raw != null ? Number(raw) : Number.NaN
      return Number.isFinite(parsed) && parsed >= 300
        ? parsed
        : DEFAULT_LEFT_PANEL_WIDTH
    } catch {
      return DEFAULT_LEFT_PANEL_WIDTH
    }
  })
  const [isResizing, setIsResizing] = useState(false)

  const startResizing = useCallback(() => {
    setIsResizing(true)
  }, [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing || !containerRef.current) return
      const containerRect = containerRef.current.getBoundingClientRect()
      // Calculate width relative to container left edge
      const newWidth = e.clientX - containerRect.left
      // Constraints: min 300px, max container width - 300px
      if (newWidth > 300 && newWidth < containerRect.width - 300) {
        setLeftPanelWidth(newWidth)
      }
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

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
        GROUPS_LEFT_PANEL_WIDTH_STORAGE_KEY,
        String(Math.round(leftPanelWidth)),
      )
    } catch {
      // Ignore persistence errors.
    }
  }, [isResizing, leftPanelWidth])

  const reloadGroups = async (
    selectId?: number | null,
    selectName?: string | null,
  ) => {
    try {
      setLoading(true)
      setError(null)
      const data = await listGroups()
      setGroups(data)

      const nameMatch = selectName
        ? data.find(
          (g) => g.name.toLowerCase() === selectName.toLowerCase(),
        )?.id ?? null
        : null

      const nextSelection =
        selectId != null
          ? selectId
          : nameMatch != null
            ? nameMatch
            : selectedGroupId != null
              ? selectedGroupId
              : data[0]?.id ?? null

      setSelectedGroupId(nextSelection)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load groups')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reloadGroups(null, preferredGroupName)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferredGroupName])

  useEffect(() => {
    let active = true
    const load = async () => {
      if (selectedGroupId == null) {
        setSelectedGroup(null)
        return
      }
      try {
        setError(null)
        const detail = await fetchGroup(selectedGroupId)
        if (!active) return
        setSelectedGroup(detail)
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load group')
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [selectedGroupId])

  const groupsById = useMemo(() => {
    const m = new Map<number, Group>()
    groups.forEach((g) => m.set(g.id, g))
    return m
  }, [groups])

  const openCreateGroup = () => {
    setGroupDialogMode('create')
    setEditingGroupId(null)
    setGroupForm(DEFAULT_GROUP_FORM)
    setGroupDialogOpen(true)
  }

  const openImportWatchlist = () => {
    setImportOpen(true)
    setImportStep(0)
    setImportFileName(null)
    setImportHeaders([])
    setImportHeaderLabels({})
    setImportRows([])
    setImportPreviewRows([])
    setImportSymbolColumn('')
    setImportExchangeColumn('')
    setImportDefaultExchange('NSE')
    setImportGroupKind('WATCHLIST')
    setImportRefQtyColumn('')
    setImportTargetWeightColumn('')
    setImportRefPriceColumn('')
    setImportStripPrefix(true)
    setImportStripSpecial(true)
    setImportSelectedColumns([])
    setImportGroupName('')
    setImportGroupDescription('')
    setImportReplaceIfExists(false)
    setImportBusy(false)
    setImportError(null)
    setImportResult(null)
  }

  const handleImportFile = async (file: File | null) => {
    if (!file) return
    try {
      setImportError(null)
      setImportBusy(true)
      const text = await file.text()
      const parsed = parseCsv(text)
      if (!parsed.headers.length) {
        setImportError('CSV has no header row.')
        return
      }
      const { keys, labels } = dedupeHeaders(parsed.headers)
      const rows: Array<Record<string, string>> = []
      for (const row of parsed.rows) {
        const obj: Record<string, string> = {}
        keys.forEach((k, i) => {
          obj[k] = String(row[i] ?? '').trim()
        })
        rows.push(obj)
      }
      setImportFileName(file.name)
      setImportHeaders(keys)
      setImportHeaderLabels(labels)
      setImportRows(rows)
      setImportPreviewRows(rows.slice(0, 10))
      const likelySymbol =
        keys.find((h) => /symbol/i.test(labels[h] ?? h)) ?? keys[0] ?? ''
      setImportSymbolColumn(likelySymbol)
      const likelyExchange = keys.find((h) => /exch/i.test(labels[h] ?? h)) ?? ''
      setImportExchangeColumn(likelyExchange)

      const defaults = keys
        .filter((h) => h !== likelySymbol && h !== likelyExchange)
        .filter((h) => disallowedColumnReason(labels[h] ?? h) == null)
      setImportSelectedColumns(defaults)
      setImportStep(1)
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Failed to read CSV.')
    } finally {
      setImportBusy(false)
    }
  }

  const isPortfolioImport =
    importGroupKind === 'MODEL_PORTFOLIO' || importGroupKind === 'PORTFOLIO'

  useEffect(() => {
    if (!isPortfolioImport || !importHeaders.length) return

    const findByLabel = (pat: RegExp) =>
      importHeaders.find((h) => pat.test(importHeaderLabels[h] ?? h)) ?? ''

    const suggestedRefQty =
      importRefQtyColumn || findByLabel(/\b(shares|qty|quantity)\b/i)
    const suggestedTargetWeight =
      importTargetWeightColumn ||
      findByLabel(/\b(weight|weightage|target\s*weight)\b/i)
    const suggestedRefPrice =
      importRefPriceColumn ||
      findByLabel(/\b(avg\s*buy|buy\s*price|ref\s*price|avg.*price)\b/i)

    if (suggestedRefQty !== importRefQtyColumn) setImportRefQtyColumn(suggestedRefQty)
    if (suggestedTargetWeight !== importTargetWeightColumn) {
      setImportTargetWeightColumn(suggestedTargetWeight)
    }
    if (suggestedRefPrice !== importRefPriceColumn) setImportRefPriceColumn(suggestedRefPrice)

    const reserved = new Set([suggestedRefQty, suggestedTargetWeight, suggestedRefPrice].filter(Boolean))
    if (reserved.size) {
      setImportSelectedColumns((prev) => prev.filter((c) => !reserved.has(c)))
    }
  }, [
    importHeaderLabels,
    importHeaders,
    importRefPriceColumn,
    importRefQtyColumn,
    importTargetWeightColumn,
    isPortfolioImport,
  ])

  const submitImportWatchlist = async () => {
    const name = importGroupName.trim()
    if (!name) {
      setImportError('Group name is required.')
      return
    }
    if (!importSymbolColumn) {
      setImportError('Select a symbol column.')
      return
    }
    if (!importRows.length) {
      setImportError('No rows found in CSV.')
      return
    }

    const existingByName = groups.find(
      (g) => g.name.toLowerCase() === name.toLowerCase(),
    )
    const conflictMode =
      existingByName && importReplaceIfExists ? 'REPLACE_DATASET' : 'ERROR'
    if (existingByName && !importReplaceIfExists) {
      setImportError(
        'A group with this name already exists. Enable “Replace existing” to overwrite.',
      )
      return
    }

    try {
      setImportBusy(true)
      setImportError(null)
      const reservedColumns = new Set<string>([
        importSymbolColumn,
        importExchangeColumn,
        ...(isPortfolioImport ? [importRefQtyColumn, importTargetWeightColumn, importRefPriceColumn] : []),
      ].filter(Boolean))
      const selectedColumns = importSelectedColumns.filter((c) => !reservedColumns.has(c))

      const res = await importWatchlistCsv({
        group_name: name,
        group_kind: importGroupKind === 'WATCHLIST' ? undefined : importGroupKind,
        group_description: importGroupDescription.trim() || null,
        source: 'TRADINGVIEW',
        original_filename: importFileName,
        symbol_column: importSymbolColumn,
        exchange_column: importExchangeColumn || null,
        default_exchange: importDefaultExchange.trim() || 'NSE',
        reference_qty_column: isPortfolioImport ? importRefQtyColumn || null : null,
        reference_price_column: isPortfolioImport ? importRefPriceColumn || null : null,
        target_weight_column: isPortfolioImport ? importTargetWeightColumn || null : null,
        target_weight_units: 'AUTO',
        selected_columns: selectedColumns,
        header_labels: importHeaderLabels,
        rows: importRows,
        strip_exchange_prefix: importStripPrefix,
        strip_special_chars: importStripSpecial,
        allow_kite_fallback: true,
        conflict_mode: conflictMode as 'ERROR' | 'REPLACE_DATASET' | 'REPLACE_GROUP',
        replace_members: true,
      })
      setImportResult({
        groupId: res.group_id,
        importedMembers: res.imported_members,
        importedColumns: res.imported_columns,
        skippedSymbols: res.skipped_symbols?.length ?? 0,
        skippedColumns: res.skipped_columns?.length ?? 0,
      })
      await reloadGroups(res.group_id)
      setImportStep(2)
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setImportBusy(false)
    }
  }

  const openEditGroup = (groupId: number) => {
    const g = groupsById.get(groupId)
    if (!g) return
    setGroupDialogMode('edit')
    setEditingGroupId(groupId)
    setGroupForm({
      name: g.name,
      kind: g.kind,
      description: g.description ?? '',
    })
    setGroupDialogOpen(true)
  }

  const submitGroupDialog = async () => {
    const name = groupForm.name.trim()
    if (!name) {
      setError('Group name is required.')
      return
    }
    try {
      setError(null)
      if (groupDialogMode === 'create') {
        const created = await createGroup({
          name,
          kind: groupForm.kind,
          description: groupForm.description.trim() || null,
        })
        setGroupDialogOpen(false)
        await reloadGroups(created.id)
      } else if (editingGroupId != null) {
        await updateGroup(editingGroupId, {
          name,
          kind: groupForm.kind,
          description: groupForm.description.trim() || null,
        })
        setGroupDialogOpen(false)
        await reloadGroups(editingGroupId)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save group')
    }
  }

  const handleDeleteGroup = async (groupId: number) => {
    const g = groupsById.get(groupId)
    const ok = window.confirm(
      `Delete group "${g?.name ?? groupId}"? This will remove all members.`,
    )
    if (!ok) return
    try {
      await deleteGroup(groupId)
      const nextSelected =
        selectedGroupId === groupId ? null : selectedGroupId
      await reloadGroups(nextSelected)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete group')
    }
  }

  const handleAddMember = async () => {
    if (!selectedGroupId) return
    const symbol = newMemberSymbol.trim().toUpperCase()
    if (!symbol) return
    try {
      setError(null)
      await addGroupMember(selectedGroupId, {
        symbol,
        exchange: newMemberExchange.trim() || null,
        notes: newMemberNotes.trim() || null,
      })
      setNewMemberSymbol('')
      setNewMemberNotes('')
      const refreshed = await fetchGroup(selectedGroupId)
      setSelectedGroup(refreshed)
      await reloadGroups(selectedGroupId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add member')
    }
  }

  useEffect(() => {
    const q = newMemberSymbol.trim()
    if (q.length < 1) {
      setSymbolOptions([])
      setSymbolOptionsError(null)
      return
    }
    let active = true
    setSymbolOptionsLoading(true)
    setSymbolOptionsError(null)
    const id = window.setTimeout(() => {
      void (async () => {
        try {
          const res = await searchMarketSymbols({
            q,
            exchange: newMemberExchange.trim().toUpperCase(),
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
  }, [newMemberExchange, newMemberSymbol])

  const handleDeleteMember = async (member: GroupMember) => {
    if (!selectedGroupId) return
    const ok = window.confirm(`Remove ${member.symbol} from this group?`)
    if (!ok) return
    try {
      setError(null)
      await deleteGroupMember(selectedGroupId, member.id)
      const refreshed = await fetchGroup(selectedGroupId)
      setSelectedGroup(refreshed)
      await reloadGroups(selectedGroupId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member')
    }
  }

  const openMemberEditor = (member: GroupMember) => {
    setMemberDraft({
      memberId: member.id,
      symbol: member.symbol,
      exchange: member.exchange ?? null,
      weightPct:
        member.target_weight != null
          ? String(Math.round(member.target_weight * 1000) / 10)
          : '',
      refQty:
        member.reference_qty != null && Number.isFinite(Number(member.reference_qty))
          ? String(Math.trunc(Number(member.reference_qty)))
          : '',
      refPrice:
        member.reference_price != null && Number.isFinite(Number(member.reference_price))
          ? Number(member.reference_price).toFixed(2)
          : '',
      notes: member.notes ?? '',
    })
    setEditMemberOpen(true)
  }

  const submitMemberEditor = async () => {
    if (!selectedGroupId || memberDraft.memberId == null) return
    let targetWeight: number | null = null
    const trimmed = memberDraft.weightPct.trim()
    if (trimmed) {
      const pct = Number(trimmed)
      if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
        setError('Target weight must be between 0 and 100.')
        return
      }
      targetWeight = pct / 100
    }
    let referenceQty: number | null | undefined
    let referencePrice: number | null | undefined
    if (selectedGroup?.kind === 'MODEL_PORTFOLIO' || selectedGroup?.kind === 'PORTFOLIO') {
      const qtyRaw = memberDraft.refQty.trim()
      if (qtyRaw === '') {
        referenceQty = null
      } else {
        const qty = Math.floor(Number(qtyRaw))
        if (!Number.isFinite(qty) || qty < 0) {
          setError('Reference qty must be a non-negative integer.')
          return
        }
        referenceQty = qty
      }

      const priceRaw = memberDraft.refPrice.trim()
      if (priceRaw === '') {
        referencePrice = null
      } else {
        const price = Number(priceRaw)
        if (!Number.isFinite(price) || price <= 0) {
          setError('Reference price must be a positive number.')
          return
        }
        referencePrice = price
      }
    }
    try {
      setError(null)
      await updateGroupMember(selectedGroupId, memberDraft.memberId, {
        target_weight: targetWeight,
        reference_qty: referenceQty,
        reference_price: referencePrice,
        notes: memberDraft.notes.trim() || null,
      })
      setEditMemberOpen(false)
      const refreshed = await fetchGroup(selectedGroupId)
      setSelectedGroup(refreshed)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update member')
    }
  }

  const handleEqualizeWeights = async () => {
    if (!selectedGroupId || !selectedGroup?.members?.length) return
    const members = selectedGroup.members
    const w = 1 / members.length
    try {
      setError(null)
      await Promise.all(
        members.map((m) =>
          updateGroupMember(selectedGroupId, m.id, { target_weight: w }),
        ),
      )
      const refreshed = await fetchGroup(selectedGroupId)
      setSelectedGroup(refreshed)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to equalize weights')
    }
  }

  const openBulkAdd = () => {
    if (!selectedGroupId) return
    setBulkState(DEFAULT_BULK_ADD)
    setBulkOpen(true)
  }

  const submitBulkAdd = async () => {
    if (!selectedGroupId) return
    const symbols = normalizeLines(bulkState.symbolsText)
    if (!symbols.length) return
    try {
      setError(null)
      await bulkAddGroupMembers(
        selectedGroupId,
        symbols.map((s) => ({ symbol: s.toUpperCase(), exchange: bulkState.exchange || null })),
      )
      setBulkOpen(false)
      const refreshed = await fetchGroup(selectedGroupId)
      setSelectedGroup(refreshed)
      await reloadGroups(selectedGroupId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add members')
    }
  }

  const computeAllocationPreview = async (draft: AllocationDraft) => {
    if (!selectedGroup?.members?.length) {
      setAllocationPreview([])
      return
    }
    const totalAmount = Number(draft.totalAmount)
    if (!Number.isFinite(totalAmount) || totalAmount <= 0) {
      setAllocationPreview([])
      return
    }

    const holdings = await fetchHoldings()
    const bySymbol = new Map<string, Holding>()
    holdings.forEach((h) => bySymbol.set(h.symbol, h))

    const weights: number[] = []
    if (draft.mode === 'weights') {
      let sum = 0
      for (const m of selectedGroup.members) {
        const w = m.target_weight ?? 0
        sum += w
      }
      if (sum <= 0) {
        weights.push(...selectedGroup.members.map(() => 1 / selectedGroup.members.length))
      } else {
        weights.push(
          ...selectedGroup.members.map((m) => (m.target_weight ?? 0) / sum),
        )
      }
    } else {
      weights.push(
        ...selectedGroup.members.map(() => 1 / selectedGroup.members.length),
      )
    }

    const rows: AllocationPreviewRow[] = selectedGroup.members.map((m, idx) => {
      const holding = bySymbol.get(m.symbol)
      const lastPrice =
        holding?.last_price != null ? Number(holding.last_price) : null
      const weightFraction = weights[idx] ?? 0
      const amount = totalAmount * weightFraction
      let qty = 0
      let warning: string | undefined
      if (!lastPrice || lastPrice <= 0) {
        warning = 'Missing last price (not in holdings?)'
      } else {
        qty = Math.floor(amount / lastPrice)
        if (qty <= 0) warning = 'Amount too small for 1 share'
        if (draft.side === 'SELL' && holding?.quantity != null) {
          qty = Math.min(qty, Number(holding.quantity))
          if (qty <= 0) warning = 'No holding qty available'
        }
      }
      return {
        id: `${m.id}`,
        symbol: m.symbol,
        exchange: m.exchange ?? null,
        weightFraction,
        amount,
        lastPrice,
        qty,
        warning,
      }
    })
    setAllocationPreview(rows)
  }

  const openAllocation = () => {
    if (!selectedGroup?.members?.length) return
    setAllocationDraft(DEFAULT_ALLOCATION)
    setAllocationPreview([])
    setAllocationError(null)
    setAllocateOpen(true)
  }

  const submitAllocation = async () => {
    if (!selectedGroup || !selectedGroup.members.length) return
    const totalAmount = Number(allocationDraft.totalAmount)
    if (!Number.isFinite(totalAmount) || totalAmount <= 0) {
      setAllocationError('Enter a valid total amount.')
      return
    }
    try {
      setAllocationError(null)
      setAllocationBusy(true)
      const preview = allocationPreview.filter((p) => p.qty > 0 && !p.warning)
      if (!preview.length) {
        setAllocationError('No valid orders to create (check last prices and amounts).')
        return
      }
      await Promise.all(
        preview.map((p) =>
          createManualOrder({
            symbol: p.symbol,
            exchange: p.exchange,
            side: allocationDraft.side,
            qty: p.qty,
            order_type: allocationDraft.orderType,
            product: allocationDraft.product,
          }),
        ),
      )
      setAllocateOpen(false)
    } catch (err) {
      setAllocationError(
        err instanceof Error ? err.message : 'Failed to create queued orders',
      )
    } finally {
      setAllocationBusy(false)
    }
  }

  const groupsColumns: GridColDef<Group>[] = [
    {
      field: 'index',
      headerName: '#',
      width: 50,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams<Group>) =>
        getPaginatedRowNumber(params),
    },
    { field: 'name', headerName: 'Name', flex: 1, minWidth: 200 },
    {
      field: 'kind',
      headerName: 'Kind',
      width: 120,
      valueFormatter: (v) =>
        GROUP_KINDS.find((k) => k.value === v)?.label ?? String(v ?? ''),
    },
    { field: 'member_count', headerName: 'Members', type: 'number', width: 100 },
    {
      field: 'updated_at',
      headerName: 'Updated',
      width: 200,
      valueFormatter: (v) =>
        formatInDisplayTimeZone(v, displayTimeZone, {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: true,
        }) || '—',
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 240,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams<Group>) => (
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            startIcon={<EditIcon />}
            onClick={(e) => {
              e.stopPropagation()
              openEditGroup(params.row.id)
            }}
          >
            Edit
          </Button>
          <Button
            color="error"
            variant="outlined"
            startIcon={<DeleteIcon />}
            onClick={(e) => {
              e.stopPropagation()
              void handleDeleteGroup(params.row.id)
            }}
          >
            Delete
          </Button>
        </Stack>
      ),
    },
  ]

  const membersColumns = useMemo((): GridColDef<GroupMember>[] => {
    const cols: GridColDef<GroupMember>[] = [
      {
        field: 'index',
        headerName: '#',
        width: 70,
        sortable: false,
        filterable: false,
        renderCell: (params: GridRenderCellParams<GroupMember>) =>
          getPaginatedRowNumber(params),
      },
      { field: 'symbol', headerName: 'Symbol', width: 160 },
      { field: 'exchange', headerName: 'Exchange', width: 120 },
      {
        field: 'target_weight',
        headerName: 'Target weight',
        width: 150,
        valueGetter: (_value, row) =>
          row.target_weight != null ? row.target_weight : null,
        valueFormatter: (v) => formatPercent(v as number | null),
      },
    ]

    if (selectedGroup?.kind === 'MODEL_PORTFOLIO' || selectedGroup?.kind === 'PORTFOLIO') {
      cols.push(
        {
          field: 'reference_qty',
          headerName: 'Ref qty',
          width: 110,
          valueGetter: (_value, row) => row.reference_qty ?? null,
        },
        {
          field: 'reference_price',
          headerName: 'Ref price',
          width: 130,
          valueGetter: (_value, row) => row.reference_price ?? null,
          valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
        },
      )
    }

    cols.push(
      { field: 'notes', headerName: 'Notes', flex: 1, minWidth: 160 },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 240,
        sortable: false,
        filterable: false,
        renderCell: (params: GridRenderCellParams<GroupMember>) => (
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<EditIcon />}
              onClick={() => openMemberEditor(params.row)}
            >
              Edit
            </Button>
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={() => void handleDeleteMember(params.row)}
            >
              Remove
            </Button>
          </Stack>
        ),
      },
    )

    return cols
  }, [selectedGroup?.kind])

  const canAllocateWithWeights =
    selectedGroup?.members?.some((m) => (m.target_weight ?? 0) > 0) ?? false

  const allocationPreviewColumns: GridColDef<AllocationPreviewRow>[] = [
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    {
      field: 'weightFraction',
      headerName: 'Weight',
      width: 110,
      valueFormatter: (v) => formatPercent(v as number | null),
    },
    {
      field: 'lastPrice',
      headerName: 'Last price',
      width: 110,
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
    },
    {
      field: 'amount',
      headerName: 'Amount',
      width: 120,
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
    },
    { field: 'qty', headerName: 'Qty', type: 'number', width: 90 },
    { field: 'warning', headerName: 'Warning', flex: 1, minWidth: 220 },
  ]

  return (
    <Box sx={{ px: 3, py: 2 }}>
      <Stack direction="row" spacing={2} alignItems="baseline">
        <Typography variant="h4">Groups</Typography>
        <Typography variant="body2" color="text.secondary">
          Create watchlists and baskets of symbols for quick filtering and batch actions.
        </Typography>
      </Stack>

      {error && (
        <Typography sx={{ mt: 1 }} color="error">
          {error}
        </Typography>
      )}

      <Box
        ref={containerRef}
        sx={{
          mt: 2,
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          gap: 0,
        }}
      >
        <Box sx={{ width: { xs: '100%', md: leftPanelWidth }, minWidth: 300, display: 'flex', flexDirection: 'column' }}>
          <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', height: '100%' }}>
	            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="h6">Groups</Typography>
              <Box sx={{ flexGrow: 1 }} />
              <Button
                startIcon={<UploadFileIcon />}
                size="small"
                variant="outlined"
                onClick={openImportWatchlist}
              >
                Import
              </Button>
              <Button
                startIcon={<AddIcon />}
                size="small"
                variant="contained"
                onClick={openCreateGroup}
              >
                New
              </Button>
            </Stack>
            <Box sx={{ mt: 1, flexGrow: 1 }}>
              <DataGrid
                rows={groups}
                columns={groupsColumns}
                loading={loading}
                getRowId={(row) => row.id}
                disableRowSelectionOnClick
                onRowClick={(params) => setSelectedGroupId(params.row.id)}
                initialState={{
                  pagination: { paginationModel: { pageSize: 10, page: 0 } },
                }}
                pageSizeOptions={[10, 25, 50]}
                sx={{
                  '& .MuiDataGrid-row.Mui-selected': {
                    bgcolor: 'action.selected',
                  },
                }}
              />
            </Box>
          </Paper>
        </Box>

        {/* Draggable Divider */}
        <Box
          onMouseDown={startResizing}
          sx={{
            width: 16,
            cursor: 'col-resize',
            display: { xs: 'none', md: 'flex' },
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            '&:hover .divider-line': {
              bgcolor: 'primary.main',
              height: '40px',
            }
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
          <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', height: '100%' }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="h6">
                {selectedGroup ? selectedGroup.name : 'Select a group'}
              </Typography>
              {selectedGroup && (
                <Chip
                  size="small"
                  label={
                    GROUP_KINDS.find((k) => k.value === selectedGroup.kind)?.label
                    ?? selectedGroup.kind
                  }
                  variant="outlined"
                />
              )}
	              <Box sx={{ flexGrow: 1 }} />
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!selectedGroupId}
                  onClick={() => {
                    if (!selectedGroupId) return
                    navigate(
                      `/holdings?${new URLSearchParams({
                        universe: `group:${selectedGroupId}`,
                      }).toString()}`,
                    )
                  }}
                >
                  Open in grid
                </Button>
              <Button
                size="small"
                variant="outlined"
                startIcon={<PlayListAddIcon />}
                disabled={!selectedGroup?.members?.length}
                onClick={openAllocation}
              >
                Allocate
              </Button>
            </Stack>

            {selectedGroup?.description && (
              <Typography sx={{ mt: 0.5 }} variant="body2" color="text.secondary">
                {selectedGroup.description}
              </Typography>
            )}

            <Divider sx={{ my: 2 }} />

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
              <Autocomplete<MarketSymbol, false, false, true>
                freeSolo
                clearOnBlur={false}
                options={symbolOptions}
                loading={symbolOptionsLoading}
                value={
                  symbolOptions.find(
                    (o) =>
                      o.symbol.toUpperCase() === newMemberSymbol.trim().toUpperCase()
                      && o.exchange.toUpperCase() === newMemberExchange.trim().toUpperCase(),
                  ) ?? null
                }
                onChange={(_e, value) => {
                  if (typeof value === 'string') {
                    setNewMemberSymbol(value.toUpperCase())
                    return
                  }
                  if (value?.symbol) setNewMemberSymbol(value.symbol.toUpperCase())
                }}
                inputValue={newMemberSymbol}
                onInputChange={(_e, value) => setNewMemberSymbol(value)}
                getOptionLabel={(o) => (typeof o === 'string' ? o : o.symbol)}
                isOptionEqualToValue={(a, b) =>
                  typeof b === 'string'
                    ? a.symbol === b
                    : a.symbol === b.symbol && a.exchange === b.exchange
                }
                renderOption={(props, option) => (
                  <li {...props} key={`${option.exchange}:${option.symbol}`}>
                    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                      <Typography variant="body2">
                        {option.symbol} <Typography component="span" variant="caption" color="text.secondary">({option.exchange})</Typography>
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
                    sx={{ width: { xs: '100%', md: 220 } }}
                    helperText={symbolOptionsError ?? undefined}
                    error={!!symbolOptionsError}
                  />
                )}
              />
              <TextField
                label="Exchange"
                size="small"
                select
                value={newMemberExchange}
                onChange={(e) => setNewMemberExchange(e.target.value)}
                sx={{ width: { xs: '100%', md: 120 } }}
              >
                <MenuItem value="NSE">NSE</MenuItem>
                <MenuItem value="BSE">BSE</MenuItem>
              </TextField>
              <TextField
                label="Notes (optional)"
                size="small"
                value={newMemberNotes}
                onChange={(e) => setNewMemberNotes(e.target.value)}
                sx={{ flexGrow: 1, width: { xs: '100%', md: 'auto' } }}
              />
              <Button
                size="small"
                variant="contained"
                startIcon={<AddIcon />}
                disabled={!selectedGroupId || !newMemberSymbol.trim()}
                onClick={() => void handleAddMember()}
              >
                Add
              </Button>
              <Button
                size="small"
                variant="outlined"
                disabled={!selectedGroupId}
                onClick={openBulkAdd}
              >
                Bulk add
              </Button>
              <Button
                size="small"
                variant="outlined"
                disabled={!selectedGroupId || !selectedGroup?.members?.length}
                onClick={() => void handleEqualizeWeights()}
              >
                Equal weights
              </Button>
            </Stack>

            <Box sx={{ mt: 1.5, flexGrow: 1 }}>
              <DataGrid
                rows={selectedGroup?.members ?? []}
                columns={membersColumns}
                getRowId={(row) => row.id}
                disableRowSelectionOnClick
                initialState={{
                  pagination: { paginationModel: { pageSize: 10, page: 0 } },
                }}
                pageSizeOptions={[10, 25, 50]}
              />
            </Box>
          </Paper>
        </Box>
      </Box>

      <Dialog open={groupDialogOpen} onClose={() => setGroupDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {groupDialogMode === 'create' ? 'Create group' : 'Edit group'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              value={groupForm.name}
              onChange={(e) =>
                setGroupForm((prev) => ({ ...prev, name: e.target.value }))
              }
              fullWidth
            />
            <FormControl fullWidth>
              <InputLabel id="group-kind-label">Kind</InputLabel>
              <Select
                labelId="group-kind-label"
                label="Kind"
                value={groupForm.kind}
                onChange={(e) =>
                  setGroupForm((prev) => ({
                    ...prev,
                    kind: e.target.value as GroupKind,
                  }))
                }
              >
                {GROUP_KINDS.map((k) => (
                  <MenuItem key={k.value} value={k.value}>
                    {k.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Description (optional)"
              value={groupForm.description}
              onChange={(e) =>
                setGroupForm((prev) => ({ ...prev, description: e.target.value }))
              }
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGroupDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => void submitGroupDialog()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Import group (CSV)</DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Stepper activeStep={importStep}>
            <Step>
              <StepLabel>Upload</StepLabel>
            </Step>
            <Step>
              <StepLabel>Map &amp; select</StepLabel>
            </Step>
            <Step>
              <StepLabel>Done</StepLabel>
            </Step>
          </Stepper>

          {importError && <Alert severity="error">{importError}</Alert>}

          {importStep === 0 && (
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Upload a TradingView (or similar) CSV export. SigmaTrader validates symbols against broker
                instruments (NSE/BSE) and only imports metadata-like columns.
              </Typography>
              <Button variant="contained" component="label" disabled={importBusy}>
                Choose CSV
                <input
                  type="file"
                  accept=".csv,text/csv"
                  hidden
                  onChange={(e) => void handleImportFile(e.target.files?.[0] ?? null)}
                />
              </Button>
              {importFileName && (
                <Typography variant="caption" sx={{ ml: 2 }}>
                  {importFileName}
                </Typography>
              )}
            </Box>
          )}

          {importStep === 1 && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
                <TextField
                  label="Group name"
                  value={importGroupName}
                  onChange={(e) => setImportGroupName(e.target.value)}
                  fullWidth
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={importReplaceIfExists}
                      onChange={(e) => setImportReplaceIfExists(e.target.checked)}
                    />
                  }
                  label="Replace existing (same name)"
                />
              </Stack>
              <TextField
                label="Description (optional)"
                value={importGroupDescription}
                onChange={(e) => setImportGroupDescription(e.target.value)}
                fullWidth
              />

              <FormControl fullWidth>
                <InputLabel id="import-group-kind-label">Group kind</InputLabel>
                <Select
                  labelId="import-group-kind-label"
                  label="Group kind"
                  value={importGroupKind}
                  onChange={(e) =>
                    setImportGroupKind(e.target.value as ImportGroupKind)
                  }
                >
                  {GROUP_KINDS.filter((k) => k.value !== 'HOLDINGS_VIEW').map((k) => (
                    <MenuItem key={k.value} value={k.value}>
                      {k.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
                <FormControl fullWidth>
                  <InputLabel>Symbol column</InputLabel>
                  <Select
                    label="Symbol column"
                    value={importSymbolColumn}
                    onChange={(e) => {
                      const next = String(e.target.value)
                      setImportSymbolColumn(next)
                      setImportSelectedColumns((prev) => prev.filter((c) => c !== next))
                    }}
                  >
                    {importHeaders.map((h) => (
                      <MenuItem key={h} value={h}>
                        {importHeaderLabels[h] ?? h}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl fullWidth>
                  <InputLabel>Exchange column</InputLabel>
                  <Select
                    label="Exchange column"
                    value={importExchangeColumn}
                    onChange={(e) => setImportExchangeColumn(String(e.target.value))}
                  >
                    <MenuItem value="">(none — use default)</MenuItem>
                    {importHeaders.map((h) => (
                      <MenuItem key={h} value={h}>
                        {importHeaderLabels[h] ?? h}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <TextField
                  label="Default exchange"
                  value={importDefaultExchange}
                  onChange={(e) => setImportDefaultExchange(e.target.value)}
                  sx={{ width: { xs: '100%', md: 160 } }}
                />
              </Stack>

              {isPortfolioImport && (
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
                  <FormControl fullWidth>
                    <InputLabel id="import-ref-qty-label">Ref qty column</InputLabel>
                    <Select
                      labelId="import-ref-qty-label"
                      label="Ref qty column"
                      value={importRefQtyColumn}
                      onChange={(e) => {
                        const next = String(e.target.value)
                        setImportRefQtyColumn(next)
                        if (next) {
                          setImportSelectedColumns((prev) => prev.filter((c) => c !== next))
                        }
                      }}
                    >
                      <MenuItem value="">(none)</MenuItem>
                      {importHeaders.map((h) => (
                        <MenuItem key={h} value={h}>
                          {importHeaderLabels[h] ?? h}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel id="import-target-weight-label">Target weight column</InputLabel>
                    <Select
                      labelId="import-target-weight-label"
                      label="Target weight column"
                      value={importTargetWeightColumn}
                      onChange={(e) => {
                        const next = String(e.target.value)
                        setImportTargetWeightColumn(next)
                        if (next) {
                          setImportSelectedColumns((prev) => prev.filter((c) => c !== next))
                        }
                      }}
                    >
                      <MenuItem value="">(none)</MenuItem>
                      {importHeaders.map((h) => (
                        <MenuItem key={h} value={h}>
                          {importHeaderLabels[h] ?? h}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel id="import-ref-price-label">Ref price column</InputLabel>
                    <Select
                      labelId="import-ref-price-label"
                      label="Ref price column"
                      value={importRefPriceColumn}
                      onChange={(e) => {
                        const next = String(e.target.value)
                        setImportRefPriceColumn(next)
                        if (next) {
                          setImportSelectedColumns((prev) => prev.filter((c) => c !== next))
                        }
                      }}
                    >
                      <MenuItem value="">(none)</MenuItem>
                      {importHeaders.map((h) => (
                        <MenuItem key={h} value={h}>
                          {importHeaderLabels[h] ?? h}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>
              )}

              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={importStripPrefix}
                      onChange={(e) => setImportStripPrefix(e.target.checked)}
                    />
                  }
                  label="Strip EXCH: prefix"
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={importStripSpecial}
                      onChange={(e) => setImportStripSpecial(e.target.checked)}
                    />
                  }
                  label="Strip special chars"
                />
              </Stack>

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Columns to import (metadata only)
                </Typography>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                    gap: 0.5,
                  }}
                >
                  {importHeaders
                    .filter((h) => h !== importSymbolColumn && h !== importExchangeColumn)
                    .map((h) => {
                      const label = importHeaderLabels[h] ?? h
                      const reason = disallowedColumnReason(label)
                      const reservedByMapping =
                        isPortfolioImport &&
                        (h === importRefQtyColumn ||
                          h === importTargetWeightColumn ||
                          h === importRefPriceColumn)
                      const checked = importSelectedColumns.includes(h)
                      return (
                        <FormControlLabel
                          key={h}
                          control={
                            <Checkbox
                              checked={checked}
                              disabled={reason != null || reservedByMapping}
                              onChange={(e) => {
                                const nextChecked = e.target.checked
                                setImportSelectedColumns((current) => {
                                  if (nextChecked) return Array.from(new Set([...current, h]))
                                  return current.filter((c) => c !== h)
                                })
                              }}
                            />
                          }
                          label={
                            reservedByMapping
                              ? `${label} (mapped)`
                              : reason
                                ? `${label} (blocked)`
                                : label
                          }
                        />
                      )
                    })}
                </Box>
                <Typography variant="caption" color="text.secondary">
                  Price/volume/performance/indicator/ratio-like fields are blocked because SigmaTrader computes them internally from candles.
                </Typography>
                {isPortfolioImport && (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                    Ref qty / target weight / ref price mappings are applied to portfolio members and are not imported as dataset columns.
                  </Typography>
                )}
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Preview (first {importPreviewRows.length} rows)
                </Typography>
                <Paper variant="outlined" sx={{ p: 1, maxHeight: 200, overflow: 'auto' }}>
                  <pre style={{ margin: 0, fontSize: 12 }}>
                    {JSON.stringify(importPreviewRows, null, 2)}
                  </pre>
                </Paper>
              </Box>
            </Box>
          )}

          {importStep === 2 && importResult && (
            <Alert severity="success">
              Imported {importResult.importedMembers} symbols with {importResult.importedColumns} columns.
              {importResult.skippedSymbols ? ` Skipped symbols: ${importResult.skippedSymbols}.` : ''}
              {importResult.skippedColumns ? ` Skipped columns: ${importResult.skippedColumns}.` : ''}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          {importStep === 1 && (
            <Button onClick={() => setImportStep(0)} disabled={importBusy}>
              Back
            </Button>
          )}
          <Button onClick={() => setImportOpen(false)} disabled={importBusy}>
            Close
          </Button>
          {importStep === 1 && (
            <Button
              variant="contained"
              onClick={() => void submitImportWatchlist()}
              disabled={importBusy || !importRows.length}
            >
              Import
            </Button>
          )}
          {importStep === 2 && importResult && (
            <Button
              variant="contained"
              onClick={() => {
                navigate(
                  `/holdings?${new URLSearchParams({
                    universe: `group:${importResult.groupId}`,
                  }).toString()}`,
                )
                setImportOpen(false)
              }}
            >
              Open in holdings grid
            </Button>
          )}
        </DialogActions>
      </Dialog>

      <Dialog open={bulkOpen} onClose={() => setBulkOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Bulk add symbols</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Exchange"
              value={bulkState.exchange}
              onChange={(e) =>
                setBulkState((prev) => ({ ...prev, exchange: e.target.value }))
              }
              helperText="Applied to all symbols in this import."
            />
            <TextField
              label="Symbols"
              value={bulkState.symbolsText}
              onChange={(e) =>
                setBulkState((prev) => ({ ...prev, symbolsText: e.target.value }))
              }
              placeholder={'BSE\nNETWEB\n...'}
              minRows={6}
              multiline
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => void submitBulkAdd()}>
            Add
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editMemberOpen} onClose={() => setEditMemberOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Edit member</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Symbol" value={memberDraft.symbol} disabled />
            <TextField
              label="Exchange"
              value={memberDraft.exchange ?? ''}
              disabled
            />
            <TextField
              label="Target weight (%)"
              value={memberDraft.weightPct}
              onChange={(e) =>
                setMemberDraft((prev) => ({ ...prev, weightPct: e.target.value }))
              }
              helperText="Optional. Leave blank for equal-weight allocations."
            />
            {(selectedGroup?.kind === 'MODEL_PORTFOLIO' || selectedGroup?.kind === 'PORTFOLIO') && (
              <>
                <TextField
                  label="Reference qty"
                  value={memberDraft.refQty}
                  onChange={(e) =>
                    setMemberDraft((prev) => ({ ...prev, refQty: e.target.value }))
                  }
                  helperText="Optional. Used for basket/portfolio 'amount required' and 'since creation' P&L."
                />
                <TextField
                  label="Reference price"
                  value={memberDraft.refPrice}
                  onChange={(e) =>
                    setMemberDraft((prev) => ({ ...prev, refPrice: e.target.value }))
                  }
                  helperText="Optional. Reference buy price at basket/portfolio creation."
                />
              </>
            )}
            <TextField
              label="Notes"
              value={memberDraft.notes}
              onChange={(e) =>
                setMemberDraft((prev) => ({ ...prev, notes: e.target.value }))
              }
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditMemberOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => void submitMemberEditor()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={allocateOpen} onClose={() => setAllocateOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Allocate funds to group members</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label="Total amount (INR)"
                value={allocationDraft.totalAmount}
                onChange={(e) =>
                  setAllocationDraft((prev) => ({
                    ...prev,
                    totalAmount: e.target.value,
                  }))
                }
                sx={{ width: { xs: '100%', md: 220 } }}
              />
              <FormControl sx={{ width: { xs: '100%', md: 160 } }}>
                <InputLabel id="alloc-side-label">Side</InputLabel>
                <Select
                  labelId="alloc-side-label"
                  label="Side"
                  value={allocationDraft.side}
                  onChange={(e) =>
                    setAllocationDraft((prev) => ({
                      ...prev,
                      side: e.target.value as 'BUY' | 'SELL',
                    }))
                  }
                >
                  <MenuItem value="BUY">BUY</MenuItem>
                  <MenuItem value="SELL">SELL</MenuItem>
                </Select>
              </FormControl>
              <FormControl sx={{ width: { xs: '100%', md: 160 } }}>
                <InputLabel id="alloc-order-type-label">Order type</InputLabel>
                <Select
                  labelId="alloc-order-type-label"
                  label="Order type"
                  value={allocationDraft.orderType}
                  onChange={(e) =>
                    setAllocationDraft((prev) => ({
                      ...prev,
                      orderType: e.target.value as 'MARKET' | 'LIMIT',
                    }))
                  }
                >
                  <MenuItem value="MARKET">MARKET</MenuItem>
                  <MenuItem value="LIMIT">LIMIT</MenuItem>
                </Select>
              </FormControl>
              <FormControl sx={{ width: { xs: '100%', md: 160 } }}>
                <InputLabel id="alloc-product-label">Product</InputLabel>
                <Select
                  labelId="alloc-product-label"
                  label="Product"
                  value={allocationDraft.product}
                  onChange={(e) =>
                    setAllocationDraft((prev) => ({
                      ...prev,
                      product: String(e.target.value),
                    }))
                  }
                >
                  <MenuItem value="CNC">CNC</MenuItem>
                  <MenuItem value="MIS">MIS</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            <FormControl>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Allocation mode
              </Typography>
              <RadioGroup
                row
                value={allocationDraft.mode}
                onChange={(e) =>
                  setAllocationDraft((prev) => ({
                    ...prev,
                    mode: e.target.value as AllocationMode,
                  }))
                }
              >
                <FormControlLabel
                  value="equal"
                  control={<Radio />}
                  label="Equal"
                />
                <FormControlLabel
                  value="weights"
                  control={<Radio />}
                  label="Target weights"
                  disabled={!canAllocateWithWeights}
                />
              </RadioGroup>
              {!canAllocateWithWeights && (
                <Typography variant="caption" color="text.secondary">
                  Add target weights to enable weighted allocations.
                </Typography>
              )}
            </FormControl>

            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="outlined"
                disabled={!selectedGroup?.members?.length}
                onClick={() =>
                  void computeAllocationPreview({
                    ...allocationDraft,
                    mode:
                      allocationDraft.mode === 'weights' && !canAllocateWithWeights
                        ? 'equal'
                        : allocationDraft.mode,
                  })
                }
              >
                Preview
              </Button>
              {allocationError && (
                <Typography color="error">{allocationError}</Typography>
              )}
            </Stack>

            <Box sx={{ height: 320 }}>
              <DataGrid
                rows={allocationPreview}
                columns={allocationPreviewColumns}
                getRowId={(r) => r.id}
                disableRowSelectionOnClick
                pageSizeOptions={[10, 25, 50]}
                initialState={{
                  pagination: { paginationModel: { pageSize: 10, page: 0 } },
                }}
              />
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAllocateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={allocationBusy || allocationPreview.length === 0}
            onClick={() => void submitAllocation()}
          >
            {allocationBusy ? 'Creating…' : 'Create queued orders'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
