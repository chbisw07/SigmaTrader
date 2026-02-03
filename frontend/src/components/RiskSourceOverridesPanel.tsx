import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
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
  deleteRiskSourceOverride,
  fetchRiskSourceOverrides,
  upsertRiskSourceOverride,
  type RiskProduct,
  type RiskSourceBucket,
  type RiskSourceOverride,
} from '../services/riskUnified'

const PRODUCTS: RiskProduct[] = ['CNC', 'MIS']
const SOURCES: RiskSourceBucket[] = ['TRADINGVIEW', 'SIGMATRADER']

type TriBool = 'INHERIT' | 'ALLOW' | 'BLOCK'

function triFrom(v: boolean | null | undefined): TriBool {
  if (v == null) return 'INHERIT'
  return v ? 'ALLOW' : 'BLOCK'
}

function triTo(v: TriBool): boolean | null {
  if (v === 'INHERIT') return null
  return v === 'ALLOW'
}

function numOrNull(raw: string): number | null {
  const s = raw.trim()
  if (!s) return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

export function RiskSourceOverridesPanel() {
  const [rows, setRows] = useState<RiskSourceOverride[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [editorOpen, setEditorOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const [draft, setDraft] = useState<RiskSourceOverride>({
    source_bucket: 'TRADINGVIEW',
    product: 'CNC',
    allow_product: null,
    allow_short_selling: null,
    max_order_value_pct: null,
    max_order_value_abs: null,
    max_quantity_per_order: null,
    order_type_policy: null,
  })

  const key = `${draft.source_bucket}:${draft.product}`

  const byKey = useMemo(() => {
    const m = new Map<string, RiskSourceOverride>()
    for (const r of rows) {
      m.set(`${r.source_bucket}:${r.product}`, r)
    }
    return m
  }, [rows])

  const load = async () => {
    setBusy(true)
    try {
      const res = await fetchRiskSourceOverrides()
      setRows(Array.isArray(res) ? res : [])
      setError(null)
    } catch (e) {
      setRows([])
      setError(e instanceof Error ? e.message : 'Failed to load source overrides')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const openCreate = () => {
    setDraft({
      source_bucket: 'TRADINGVIEW',
      product: 'CNC',
      allow_product: null,
      allow_short_selling: null,
      max_order_value_pct: null,
      max_order_value_abs: null,
      max_quantity_per_order: null,
      order_type_policy: null,
    })
    setEditorOpen(true)
  }

  const openEdit = (row: RiskSourceOverride) => {
    setDraft({
      ...row,
      allow_product: row.allow_product ?? null,
      allow_short_selling: row.allow_short_selling ?? null,
      max_order_value_pct: row.max_order_value_pct ?? null,
      max_order_value_abs: row.max_order_value_abs ?? null,
      max_quantity_per_order: row.max_quantity_per_order ?? null,
      order_type_policy: row.order_type_policy ?? null,
    })
    setEditorOpen(true)
  }

  const current = byKey.get(key)

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Source overrides
        </Typography>
        <Tooltip title="Refresh" arrow placement="top">
          <span>
            <IconButton size="small" onClick={() => void load()} disabled={busy}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
          New override
        </Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        Optional per-source caps that layer on top of product profiles. Leave fields blank to inherit.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mt: 1.5 }}>
          {error}
        </Alert>
      )}

      <Box sx={{ mt: 1.5 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Source</TableCell>
              <TableCell>Product</TableCell>
              <TableCell>Allow</TableCell>
              <TableCell>Shorts</TableCell>
              <TableCell>Max order %</TableCell>
              <TableCell>Max order abs</TableCell>
              <TableCell>Max qty</TableCell>
              <TableCell>Order types</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length ? (
              rows.map((r) => (
                <TableRow key={`${r.source_bucket}:${r.product}`}>
                  <TableCell>{r.source_bucket}</TableCell>
                  <TableCell>{r.product}</TableCell>
                  <TableCell>{triFrom(r.allow_product)}</TableCell>
                  <TableCell>{triFrom(r.allow_short_selling)}</TableCell>
                  <TableCell>{r.max_order_value_pct ?? '—'}</TableCell>
                  <TableCell>{r.max_order_value_abs ?? '—'}</TableCell>
                  <TableCell>{r.max_quantity_per_order ?? '—'}</TableCell>
                  <TableCell>{r.order_type_policy ?? '—'}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(r)}>
                      Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={9} sx={{ color: 'text.secondary' }}>
                  {busy ? 'Loading…' : 'No overrides configured.'}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Box>

      <Dialog open={editorOpen} onClose={() => setEditorOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{current ? 'Edit override' : 'New override'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'grid', gap: 1.5, mt: 1, gridTemplateColumns: '1fr 1fr' }}>
            <FormControl size="small">
              <InputLabel>Source</InputLabel>
              <Select
                value={draft.source_bucket}
                label="Source"
                onChange={(e) =>
                  setDraft((p) => ({ ...p, source_bucket: e.target.value as RiskSourceBucket }))
                }
              >
                {SOURCES.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small">
              <InputLabel>Product</InputLabel>
              <Select
                value={draft.product}
                label="Product"
                onChange={(e) =>
                  setDraft((p) => ({ ...p, product: e.target.value as RiskProduct }))
                }
              >
                {PRODUCTS.map((p) => (
                  <MenuItem key={p} value={p}>
                    {p}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ display: 'grid', gap: 1.5, mt: 2, gridTemplateColumns: '1fr 1fr' }}>
            <FormControl size="small">
              <InputLabel>Allow product</InputLabel>
              <Select
                value={triFrom(draft.allow_product)}
                label="Allow product"
                onChange={(e) =>
                  setDraft((p) => ({ ...p, allow_product: triTo(e.target.value as TriBool) }))
                }
              >
                <MenuItem value="INHERIT">INHERIT</MenuItem>
                <MenuItem value="ALLOW">ALLOW</MenuItem>
                <MenuItem value="BLOCK">BLOCK</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small">
              <InputLabel>Short selling</InputLabel>
              <Select
                value={triFrom(draft.allow_short_selling)}
                label="Short selling"
                onChange={(e) =>
                  setDraft((p) => ({
                    ...p,
                    allow_short_selling: triTo(e.target.value as TriBool),
                  }))
                }
              >
                <MenuItem value="INHERIT">INHERIT</MenuItem>
                <MenuItem value="ALLOW">ALLOW</MenuItem>
                <MenuItem value="BLOCK">BLOCK</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ display: 'grid', gap: 1.5, mt: 2, gridTemplateColumns: '1fr 1fr' }}>
            <TextField
              size="small"
              label="Max order value (%)"
              value={draft.max_order_value_pct ?? ''}
              onChange={(e) => setDraft((p) => ({ ...p, max_order_value_pct: numOrNull(e.target.value) }))}
              helperText="Optional. Uses baseline equity."
            />
            <TextField
              size="small"
              label="Max order value (abs)"
              value={draft.max_order_value_abs ?? ''}
              onChange={(e) => setDraft((p) => ({ ...p, max_order_value_abs: numOrNull(e.target.value) }))}
              helperText="Optional absolute cap."
            />
            <TextField
              size="small"
              label="Max qty per order"
              value={draft.max_quantity_per_order ?? ''}
              onChange={(e) =>
                setDraft((p) => ({ ...p, max_quantity_per_order: numOrNull(e.target.value) }))
              }
              helperText="Optional."
            />
            <TextField
              size="small"
              label="Order type policy"
              value={draft.order_type_policy ?? ''}
              onChange={(e) => setDraft((p) => ({ ...p, order_type_policy: e.target.value || null }))}
              helperText='Comma-separated allowlist (e.g. "MARKET,LIMIT,SL,SL-M").'
            />
          </Box>

          {current && (
            <Alert severity="info" sx={{ mt: 2 }}>
              This override will take effect for new executions; leave blank fields as INHERIT to
              use product profile defaults.
            </Alert>
          )}
        </DialogContent>
        <DialogActions sx={{ justifyContent: 'space-between' }}>
          <Box>
            {current ? (
              <Button
                color="error"
                startIcon={<DeleteIcon />}
                disabled={saving || deleting}
                onClick={async () => {
                  const confirmed = window.confirm('Delete this override?')
                  if (!confirmed) return
                  setDeleting(true)
                  try {
                    await deleteRiskSourceOverride({
                      source_bucket: draft.source_bucket,
                      product: draft.product,
                    })
                    setEditorOpen(false)
                    await load()
                  } catch (e) {
                    setError(e instanceof Error ? e.message : 'Failed to delete override')
                  } finally {
                    setDeleting(false)
                  }
                }}
              >
                Delete
              </Button>
            ) : null}
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button onClick={() => setEditorOpen(false)} disabled={saving || deleting}>
              Cancel
            </Button>
            <Button
              variant="contained"
              disabled={saving || deleting}
              onClick={async () => {
                setSaving(true)
                try {
                  await upsertRiskSourceOverride({
                    source_bucket: draft.source_bucket,
                    product: draft.product,
                    allow_product: draft.allow_product ?? null,
                    allow_short_selling: draft.allow_short_selling ?? null,
                    max_order_value_pct: draft.max_order_value_pct ?? null,
                    max_order_value_abs: draft.max_order_value_abs ?? null,
                    max_quantity_per_order: draft.max_quantity_per_order ?? null,
                    order_type_policy: (draft.order_type_policy || '').trim() || null,
                  })
                  setEditorOpen(false)
                  await load()
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Failed to save override')
                } finally {
                  setSaving(false)
                }
              }}
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </Box>
        </DialogActions>
      </Dialog>
    </Paper>
  )
}

