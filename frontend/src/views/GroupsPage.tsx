import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import PlayListAddIcon from '@mui/icons-material/PlaylistAdd'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
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
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { createManualOrder } from '../services/orders'
import { fetchHoldings, type Holding } from '../services/positions'
import {
  addGroupMember,
  bulkAddGroupMembers,
  createGroup,
  deleteGroup,
  deleteGroupMember,
  fetchGroup,
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

function normalizeLines(text: string): string[] {
  return text
    .split(/[\n,]+/g)
    .map((s) => s.trim())
    .filter(Boolean)
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

export function GroupsPage() {
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

  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkState, setBulkState] = useState<BulkAddState>(DEFAULT_BULK_ADD)

  const [editMemberOpen, setEditMemberOpen] = useState(false)
  const [memberDraft, setMemberDraft] = useState<{
    memberId: number | null
    symbol: string
    exchange?: string | null
    weightPct: string
    notes: string
  }>({
    memberId: null,
    symbol: '',
    exchange: null,
    weightPct: '',
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

  // Resizable panel state
  const containerRef = useRef<HTMLDivElement>(null)
  const [leftPanelWidth, setLeftPanelWidth] = useState(800)
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
    try {
      setError(null)
      await updateGroupMember(selectedGroupId, memberDraft.memberId, {
        target_weight: targetWeight,
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
    { field: 'name', headerName: 'Name', flex: 1, minWidth: 200 },
    {
      field: 'kind',
      headerName: 'Kind',
      width: 140,
      valueFormatter: (v) =>
        GROUP_KINDS.find((k) => k.value === v)?.label ?? String(v ?? ''),
    },
    { field: 'member_count', headerName: 'Members', type: 'number', width: 100 },
    {
      field: 'updated_at',
      headerName: 'Updated',
      width: 170,
      valueFormatter: (v) => (v ? new Date(String(v)).toLocaleString() : '—'),
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

  const membersColumns: GridColDef<GroupMember>[] = [
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
  ]

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
              <TextField
                label="Symbol"
                size="small"
                value={newMemberSymbol}
                onChange={(e) => setNewMemberSymbol(e.target.value)}
                sx={{ width: { xs: '100%', md: 180 } }}
              />
              <TextField
                label="Exchange"
                size="small"
                value={newMemberExchange}
                onChange={(e) => setNewMemberExchange(e.target.value)}
                sx={{ width: { xs: '100%', md: 120 } }}
              />
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
