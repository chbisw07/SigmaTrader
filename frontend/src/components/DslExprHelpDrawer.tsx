import AddIcon from '@mui/icons-material/Add'
import CloseIcon from '@mui/icons-material/Close'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import EditIcon from '@mui/icons-material/Edit'
import SearchIcon from '@mui/icons-material/Search'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState } from 'react'

import {
  buildDslCatalog,
  loadUserDslCatalogItems,
  saveUserDslCatalogItems,
  type DslCatalogItem,
  type DslCatalogKind,
  type UserDslCatalogItem,
} from '../services/dslCatalog'

type CustomIndicator = {
  name: string
  params?: string[]
  description?: string | null
}

export function DslExprHelpDrawer({
  open,
  onClose,
  operands,
  customIndicators,
  onInsert,
  title = 'DSL expression help',
}: {
  open: boolean
  onClose: () => void
  operands?: string[]
  customIndicators?: CustomIndicator[]
  onInsert: (text: string) => void
  title?: string
}) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<DslCatalogKind | 'all'>('all')
  const [userItems, setUserItems] = useState<UserDslCatalogItem[]>([])
  const [editOpen, setEditOpen] = useState(false)
  const [editMode, setEditMode] = useState<'add' | 'edit'>('add')
  const [editExpr, setEditExpr] = useState('')
  const [editSignature, setEditSignature] = useState('')
  const [editDetails, setEditDetails] = useState('')
  const [editError, setEditError] = useState<string | null>(null)
  const [editOriginalExpr, setEditOriginalExpr] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setUserItems(loadUserDslCatalogItems())
  }, [open])

  useEffect(() => {
    if (!open) return
    saveUserDslCatalogItems(userItems)
  }, [open, userItems])

  const items = useMemo(() => {
    const catalog = buildDslCatalog({ operands, customIndicators, userItems })
    const q = query.trim().toLowerCase()
    const filtered = catalog.filter((it) => {
      if (kind !== 'all' && it.kind !== kind) return false
      if (!q) return true
      return (
        it.expr.toLowerCase().includes(q) ||
        it.signature.toLowerCase().includes(q) ||
        it.details.toLowerCase().includes(q)
      )
    })
    const rank: Record<DslCatalogKind, number> = {
      user: 0,
      function: 1,
      metric: 2,
      variable: 3,
      custom_indicator: 4,
      keyword: 5,
      source: 6,
    }
    return filtered.sort((a, b) => {
      const ra = rank[a.kind] ?? 99
      const rb = rank[b.kind] ?? 99
      if (ra !== rb) return ra - rb
      return a.expr.localeCompare(b.expr)
    })
  }, [customIndicators, kind, operands, query, userItems])

  const kindChips: Array<{ label: string; value: DslCatalogKind | 'all' }> = [
    { label: 'All', value: 'all' },
    { label: 'User', value: 'user' },
    { label: 'Functions', value: 'function' },
    { label: 'Metrics', value: 'metric' },
    { label: 'Variables', value: 'variable' },
    { label: 'Custom', value: 'custom_indicator' },
    { label: 'Keywords', value: 'keyword' },
    { label: 'Sources', value: 'source' },
  ]

  const openAdd = () => {
    setEditMode('add')
    setEditExpr('')
    setEditSignature('')
    setEditDetails('')
    setEditOriginalExpr(null)
    setEditError(null)
    setEditOpen(true)
  }

  const openEdit = (item: UserDslCatalogItem) => {
    setEditMode('edit')
    setEditExpr(item.expr)
    setEditSignature(item.signature)
    setEditDetails(item.details)
    setEditOriginalExpr(item.expr)
    setEditError(null)
    setEditOpen(true)
  }

  const saveEdit = () => {
    const expr = editExpr.trim()
    const signature = editSignature.trim()
    const details = editDetails.trim()
    if (!expr) {
      setEditError('Expr is required.')
      return
    }
    if (!signature) {
      setEditError('Signature is required.')
      return
    }
    const normalizedExpr = expr
    const exists = userItems.some(
      (x) =>
        x.expr.trim().toLowerCase() === normalizedExpr.toLowerCase() &&
        (editMode === 'add' || x.expr.trim().toLowerCase() !== (editOriginalExpr || '').trim().toLowerCase()),
    )
    if (exists) {
      setEditError('A user entry with this Expr already exists.')
      return
    }

    if (editMode === 'add') {
      setUserItems((cur) => [...cur, { expr: normalizedExpr, signature, details }])
    } else {
      setUserItems((cur) =>
        cur.map((x) =>
          x.expr.trim().toLowerCase() === (editOriginalExpr || '').trim().toLowerCase()
            ? { expr: normalizedExpr, signature, details }
            : x,
        ),
      )
    }
    setEditOpen(false)
  }

  const deleteUser = (expr: string) => {
    setUserItems((cur) => cur.filter((x) => x.expr !== expr))
  }

  const exportUser = async () => {
    const payload = JSON.stringify(userItems, null, 2)
    try {
      await navigator.clipboard.writeText(payload)
    } catch {
      // fallback: open import dialog prefilled, so user can copy manually
      setImportText(payload)
      setImportError(null)
      setImportOpen(true)
    }
  }

  const applyImport = () => {
    setImportError(null)
    try {
      const parsed = JSON.parse(importText) as unknown
      if (!Array.isArray(parsed)) {
        setImportError('Import must be a JSON array of {expr, signature, details}.')
        return
      }
      const cleaned: UserDslCatalogItem[] = []
      for (const x of parsed) {
        if (!x || typeof x !== 'object') continue
        const rec = x as any
        const expr = String(rec.expr ?? '').trim()
        const signature = String(rec.signature ?? '').trim()
        const details = String(rec.details ?? '').trim()
        if (!expr || !signature) continue
        cleaned.push({ expr, signature, details })
      }
      if (cleaned.length === 0) {
        setImportError('No valid items found.')
        return
      }
      setUserItems((cur) => {
        const map = new Map(cur.map((x) => [x.expr.toLowerCase(), x]))
        for (const x of cleaned) map.set(x.expr.toLowerCase(), x)
        return Array.from(map.values())
      })
      setImportOpen(false)
    } catch {
      setImportError('Invalid JSON.')
    }
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100vw', sm: 560 },
          maxWidth: '100vw',
          p: 2,
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
          <Typography variant="h6">{title}</Typography>
          <Typography variant="caption" color="text.secondary">
            Click a row to insert into the editor.
          </Typography>
        </Box>
        <Tooltip title="Add to this table (saved in your browser)">
          <IconButton aria-label="Add" onClick={openAdd}>
            <AddIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Import / paste user entries">
          <IconButton
            aria-label="Import"
            onClick={() => {
              setImportText('')
              setImportError(null)
              setImportOpen(true)
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              JSON
            </Typography>
          </IconButton>
        </Tooltip>
        <Tooltip title="Export user entries (copy JSON to clipboard)">
          <span>
            <Button size="small" variant="text" onClick={() => void exportUser()}>
              Export
            </Button>
          </span>
        </Tooltip>
        <IconButton aria-label="Close" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </Box>

      <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        {kindChips.map((c) => (
          <Chip
            key={c.value}
            size="small"
            label={c.label}
            color={kind === c.value ? 'primary' : 'default'}
            variant={kind === c.value ? 'filled' : 'outlined'}
            onClick={() => setKind(c.value)}
          />
        ))}
      </Box>

      <TextField
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search… (e.g. SMA, PNL_PCT, crosses)"
        size="small"
        fullWidth
        sx={{ mt: 2 }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
      />

      <Divider sx={{ my: 2 }} />

      <Box sx={{ flex: 1, overflow: 'auto' }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: 140 }}>Expr</TableCell>
              <TableCell sx={{ width: 240 }}>Signature</TableCell>
              <TableCell>Details</TableCell>
              <TableCell sx={{ width: 86 }} />
            </TableRow>
          </TableHead>
          <TableBody>
            {items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4}>
                  <Typography variant="body2" color="text.secondary">
                    No matches.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              items.map((it) => (
                <DslRow
                  key={`${it.kind}:${it.expr}:${it.signature}`}
                  item={it}
                  onInsert={onInsert}
                  onEditUser={
                    it.kind === 'user'
                      ? () => {
                          const found = userItems.find((x) => x.expr === it.expr)
                          if (found) openEdit(found)
                        }
                      : undefined
                  }
                  onDeleteUser={
                    it.kind === 'user'
                      ? () => deleteUser(it.expr)
                      : undefined
                  }
                />
              ))
            )}
          </TableBody>
        </Table>
      </Box>

      <Dialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{editMode === 'add' ? 'Add DSL help entry' : 'Edit DSL help entry'}</DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField
            label="Expr"
            value={editExpr}
            onChange={(e) => setEditExpr(e.target.value)}
            autoFocus
            helperText="Displayed name (e.g. SMA, MY_SNIPPET, PNL_PCT)."
          />
          <TextField
            label="Signature"
            value={editSignature}
            onChange={(e) => setEditSignature(e.target.value)}
            helperText={'Inserted into the editor when clicked (e.g. SMA(close, 14, "1d")).'}
          />
          <TextField
            label="Details"
            value={editDetails}
            onChange={(e) => setEditDetails(e.target.value)}
            helperText="Optional: what it does / when to use."
            multiline
            minRows={3}
          />
          {editError && (
            <Typography variant="body2" color="error">
              {editError}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary">
            Saved locally in your browser. Use Export/JSON to move it to another machine.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={saveEdit}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={importOpen} onClose={() => setImportOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Import / Paste JSON</DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField
            label="User DSL help entries (JSON array)"
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder='[{"expr":"MY_SNIP","signature":"SMA(close, 20, \"1d\")","details":"..."}]'
            multiline
            minRows={8}
          />
          {importError && (
            <Typography variant="body2" color="error">
              {importError}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary">
            Import merges by Expr (case-insensitive). Existing entries with the same Expr will be overwritten.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={applyImport}>
            Import
          </Button>
        </DialogActions>
      </Dialog>
    </Drawer>
  )
}

function DslRow({
  item,
  onInsert,
  onEditUser,
  onDeleteUser,
}: {
  item: DslCatalogItem
  onInsert: (text: string) => void
  onEditUser?: () => void
  onDeleteUser?: () => void
}) {
  return (
    <TableRow
      hover
      sx={{ cursor: 'pointer' }}
      onClick={() => onInsert(item.insertText ?? item.signature)}
    >
      <TableCell>
        <Typography variant="body2">
          <code>{item.expr}</code>
        </Typography>
      </TableCell>
      <TableCell>
        <Typography variant="body2" component="div" sx={{ whiteSpace: 'nowrap' }}>
          <code>{item.signature}</code>
        </Typography>
      </TableCell>
      <TableCell>
        <Tooltip title={item.details}>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: 280,
            }}
          >
            {item.details}
          </Typography>
        </Tooltip>
      </TableCell>
      <TableCell align="right">
        {onEditUser && onDeleteUser ? (
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 0.5 }}>
            <Tooltip title="Edit">
              <IconButton
                size="small"
                onClick={(e) => {
                  e.stopPropagation()
                  onEditUser()
                }}
              >
                <EditIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete">
              <IconButton
                size="small"
                color="error"
                onClick={(e) => {
                  e.stopPropagation()
                  onDeleteUser()
                }}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        ) : null}
      </TableCell>
    </TableRow>
  )
}
