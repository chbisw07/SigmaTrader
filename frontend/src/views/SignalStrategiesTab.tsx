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
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import { useEffect, useMemo, useState } from 'react'

import type { AlertVariableDef } from '../services/alertsV3'
import {
  createSignalStrategy,
  createSignalStrategyVersion,
  deleteSignalStrategy,
  exportSignalStrategy,
  importSignalStrategy,
  listSignalStrategies,
  listSignalStrategyVersions,
  updateSignalStrategy,
  type SignalStrategy,
  type SignalStrategyInputDef,
  type SignalStrategyOutputDef,
  type SignalStrategyParamType,
  type SignalStrategyRegime,
  type SignalStrategyScope,
  type SignalStrategyVersion,
} from '../services/signalStrategies'

function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function parseCsvList(raw: string): string[] {
  return raw
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}

function emptyVariable(): AlertVariableDef {
  return { name: '', dsl: '', kind: 'DSL', params: null }
}

function emptyInput(): SignalStrategyInputDef {
  return { name: '', type: 'number', default: undefined, enum_values: null }
}

function emptyOutput(): SignalStrategyOutputDef {
  return { name: '', kind: 'SIGNAL', dsl: '' }
}

function sanitizeVersionDraft(draft: SignalStrategyVersionDraft): SignalStrategyVersionDraft {
  return {
    enabled: Boolean(draft.enabled),
    inputs: (draft.inputs ?? [])
      .map((i) => ({
        name: (i.name || '').trim(),
        type: i.type,
        default: i.default,
        enum_values: Array.isArray(i.enum_values) ? i.enum_values : null,
      }))
      .filter((i) => i.name),
    variables: (draft.variables ?? [])
      .map((v) => ({
        name: (v.name || '').trim(),
        dsl: (v.dsl || '').trim(),
        kind: v.kind ?? 'DSL',
        params: v.params ?? null,
      }))
      .filter((v) => v.name && v.dsl),
    outputs: (draft.outputs ?? [])
      .map((o) => ({
        name: (o.name || '').trim(),
        kind: o.kind,
        dsl: (o.dsl || '').trim(),
        plot: o.plot ?? null,
      }))
      .filter((o) => o.name && o.dsl),
  }
}

type SignalStrategyVersionDraft = {
  enabled: boolean
  inputs: SignalStrategyInputDef[]
  variables: AlertVariableDef[]
  outputs: SignalStrategyOutputDef[]
}

function makeDraftFromVersion(v: SignalStrategyVersion | null): SignalStrategyVersionDraft {
  if (!v) {
    return { enabled: true, inputs: [], variables: [], outputs: [] }
  }
  return {
    enabled: v.enabled,
    inputs: v.inputs ?? [],
    variables: v.variables ?? [],
    outputs: v.outputs ?? [],
  }
}

function StrategyVersionEditor({
  draft,
  onChange,
}: {
  draft: SignalStrategyVersionDraft
  onChange: (next: SignalStrategyVersionDraft) => void
}) {
  const setInputs = (inputs: SignalStrategyInputDef[]) => onChange({ ...draft, inputs })
  const setVariables = (variables: AlertVariableDef[]) =>
    onChange({ ...draft, variables })
  const setOutputs = (outputs: SignalStrategyOutputDef[]) => onChange({ ...draft, outputs })

  return (
    <Stack spacing={2}>
      <FormControlLabel
        control={
          <Switch
            checked={draft.enabled}
            onChange={(e) => onChange({ ...draft, enabled: e.target.checked })}
          />
        }
        label="Enabled"
      />

      <Box>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Inputs (parameters)</Typography>
          <Button size="small" onClick={() => setInputs([...draft.inputs, emptyInput()])}>
            Add input
          </Button>
        </Stack>
        <Stack spacing={1}>
          {draft.inputs.map((inp, idx) => (
            <Stack key={idx} direction="row" spacing={1} alignItems="center">
              <TextField
                label="Name"
                size="small"
                value={inp.name ?? ''}
                onChange={(e) =>
                  setInputs(
                    draft.inputs.map((x, i) => (i === idx ? { ...x, name: e.target.value } : x)),
                  )
                }
                sx={{ width: 180 }}
              />
              <TextField
                label="Type"
                select
                size="small"
                value={inp.type}
                onChange={(e) =>
                  setInputs(
                    draft.inputs.map((x, i) =>
                      i === idx ? { ...x, type: e.target.value as SignalStrategyParamType } : x,
                    ),
                  )
                }
                sx={{ width: 140 }}
              >
                <MenuItem value="number">number</MenuItem>
                <MenuItem value="bool">bool</MenuItem>
                <MenuItem value="string">string</MenuItem>
                <MenuItem value="timeframe">timeframe</MenuItem>
                <MenuItem value="enum">enum</MenuItem>
              </TextField>
              <TextField
                label="Default"
                size="small"
                value={inp.default == null ? '' : String(inp.default)}
                onChange={(e) =>
                  setInputs(
                    draft.inputs.map((x, i) => (i === idx ? { ...x, default: e.target.value } : x)),
                  )
                }
                sx={{ width: 180 }}
              />
              {inp.type === 'enum' ? (
                <TextField
                  label="Enum values (comma)"
                  size="small"
                  value={(inp.enum_values ?? []).join(', ')}
                  onChange={(e) =>
                    setInputs(
                      draft.inputs.map((x, i) =>
                        i === idx ? { ...x, enum_values: parseCsvList(e.target.value) } : x,
                      ),
                    )
                  }
                  sx={{ flex: 1 }}
                />
              ) : (
                <Box sx={{ flex: 1 }} />
              )}
              <Button
                size="small"
                color="error"
                onClick={() => setInputs(draft.inputs.filter((_x, i) => i !== idx))}
              >
                Remove
              </Button>
            </Stack>
          ))}
          {draft.inputs.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No inputs. Add parameters if you want to reuse the same strategy with different lengths/thresholds.
            </Typography>
          )}
        </Stack>
      </Box>

      <Box>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Variables</Typography>
          <Button
            size="small"
            onClick={() => setVariables([...draft.variables, emptyVariable()])}
          >
            Add variable
          </Button>
        </Stack>
        <Stack spacing={1}>
          {draft.variables.map((v, idx) => (
            <Stack key={idx} direction="row" spacing={1} alignItems="flex-start">
              <TextField
                label="Name"
                size="small"
                value={v.name ?? ''}
                onChange={(e) =>
                  setVariables(
                    draft.variables.map((x, i) => (i === idx ? { ...x, name: e.target.value } : x)),
                  )
                }
                sx={{ width: 180 }}
              />
              <TextField
                label="DSL"
                size="small"
                multiline
                minRows={1}
                maxRows={3}
                value={v.dsl ?? ''}
                onChange={(e) =>
                  setVariables(
                    draft.variables.map((x, i) => (i === idx ? { ...x, dsl: e.target.value } : x)),
                  )
                }
                sx={{ flex: 1 }}
              />
              <Button
                size="small"
                color="error"
                onClick={() => setVariables(draft.variables.filter((_x, i) => i !== idx))}
              >
                Remove
              </Button>
            </Stack>
          ))}
          {draft.variables.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No variables. You can still define outputs directly.
            </Typography>
          )}
        </Stack>
      </Box>

      <Box>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Outputs</Typography>
          <Button size="small" onClick={() => setOutputs([...draft.outputs, emptyOutput()])}>
            Add output
          </Button>
        </Stack>
        <Stack spacing={1}>
          {draft.outputs.map((o, idx) => (
            <Stack key={idx} direction="row" spacing={1} alignItems="flex-start">
              <TextField
                label="Name"
                size="small"
                value={o.name ?? ''}
                onChange={(e) =>
                  setOutputs(
                    draft.outputs.map((x, i) => (i === idx ? { ...x, name: e.target.value } : x)),
                  )
                }
                sx={{ width: 180 }}
              />
              <TextField
                label="Kind"
                select
                size="small"
                value={o.kind}
                onChange={(e) =>
                  setOutputs(
                    draft.outputs.map((x, i) =>
                      i === idx
                        ? { ...x, kind: e.target.value as 'SIGNAL' | 'OVERLAY' }
                        : x,
                    ),
                  )
                }
                sx={{ width: 130 }}
              >
                <MenuItem value="SIGNAL">SIGNAL</MenuItem>
                <MenuItem value="OVERLAY">OVERLAY</MenuItem>
              </TextField>
              <TextField
                label="DSL"
                size="small"
                multiline
                minRows={2}
                maxRows={6}
                value={o.dsl ?? ''}
                onChange={(e) =>
                  setOutputs(
                    draft.outputs.map((x, i) => (i === idx ? { ...x, dsl: e.target.value } : x)),
                  )
                }
                sx={{ flex: 1 }}
              />
              <Button
                size="small"
                color="error"
                onClick={() => setOutputs(draft.outputs.filter((_x, i) => i !== idx))}
              >
                Remove
              </Button>
            </Stack>
          ))}
          {draft.outputs.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              At least one output is required. Use kind SIGNAL for alerts/screener, and OVERLAY for dashboard plots.
            </Typography>
          )}
        </Stack>
      </Box>
    </Stack>
  )
}

function StrategyCreateDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: () => void
}) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [scope, setScope] = useState<SignalStrategyScope>('USER')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [regimes, setRegimes] = useState<SignalStrategyRegime[]>([])
  const [versionDraft, setVersionDraft] = useState<SignalStrategyVersionDraft>({
    enabled: true,
    inputs: [],
    variables: [],
    outputs: [],
  })

  useEffect(() => {
    if (!open) return
    setSaving(false)
    setError(null)
    setName('')
    setScope('USER')
    setDescription('')
    setTags('')
    setRegimes([])
    setVersionDraft({ enabled: true, inputs: [], variables: [], outputs: [] })
  }, [open])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const draft = sanitizeVersionDraft(versionDraft)
      await createSignalStrategy({
        name: name.trim(),
        description: description.trim() || null,
        tags: parseCsvList(tags),
        regimes,
        scope,
        version: { ...draft, enabled: draft.enabled },
      })
      onCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create strategy')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Create strategy (DSL V3)</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {error && <Typography color="error">{error}</Typography>}
          <Stack direction="row" spacing={1}>
            <TextField
              label="Name"
              fullWidth
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <TextField
              label="Scope"
              select
              value={scope}
              onChange={(e) => setScope(e.target.value as SignalStrategyScope)}
              sx={{ width: 140 }}
            >
              <MenuItem value="USER">USER</MenuItem>
              <MenuItem value="GLOBAL">GLOBAL</MenuItem>
            </TextField>
          </Stack>
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              label="Tags (comma-separated)"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              fullWidth
            />
            <TextField
              label="Regimes"
              select
              SelectProps={{ multiple: true }}
              value={regimes}
              onChange={(e) => {
                const v = e.target.value
                setRegimes(Array.isArray(v) ? (v as SignalStrategyRegime[]) : [])
              }}
              sx={{ width: 220 }}
            >
              <MenuItem value="BULL">BULL</MenuItem>
              <MenuItem value="SIDEWAYS">SIDEWAYS</MenuItem>
              <MenuItem value="BEAR">BEAR</MenuItem>
            </TextField>
          </Stack>

          <StrategyVersionEditor draft={versionDraft} onChange={setVersionDraft} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void save()} disabled={saving || !name.trim()}>
          {saving ? 'Saving…' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

function StrategyMetadataDialog({
  open,
  strategy,
  onClose,
  onUpdated,
}: {
  open: boolean
  strategy: SignalStrategy | null
  onClose: () => void
  onUpdated: () => void
}) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [scope, setScope] = useState<SignalStrategyScope>('USER')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [regimes, setRegimes] = useState<SignalStrategyRegime[]>([])

  useEffect(() => {
    if (!open) return
    setSaving(false)
    setError(null)
    setName(strategy?.name ?? '')
    setScope(strategy?.scope ?? 'USER')
    setDescription(strategy?.description ?? '')
    setTags((strategy?.tags ?? []).join(', '))
    setRegimes((strategy?.regimes ?? []) as SignalStrategyRegime[])
  }, [open, strategy])

  const save = async () => {
    if (!strategy) return
    setSaving(true)
    setError(null)
    try {
      await updateSignalStrategy(strategy.id, {
        name: name.trim(),
        scope,
        description: description.trim() || null,
        tags: parseCsvList(tags),
        regimes,
      })
      onUpdated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update strategy')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Edit strategy</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {error && <Typography color="error">{error}</Typography>}
          <Stack direction="row" spacing={1}>
            <TextField
              label="Name"
              fullWidth
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <TextField
              label="Scope"
              select
              value={scope}
              onChange={(e) => setScope(e.target.value as SignalStrategyScope)}
              sx={{ width: 140 }}
            >
              <MenuItem value="USER">USER</MenuItem>
              <MenuItem value="GLOBAL">GLOBAL</MenuItem>
            </TextField>
          </Stack>
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
          <TextField
            label="Tags (comma-separated)"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            fullWidth
          />
          <TextField
            label="Regimes"
            select
            SelectProps={{ multiple: true }}
            value={regimes}
            onChange={(e) => {
              const v = e.target.value
              setRegimes(Array.isArray(v) ? (v as SignalStrategyRegime[]) : [])
            }}
          >
            <MenuItem value="BULL">BULL</MenuItem>
            <MenuItem value="SIDEWAYS">SIDEWAYS</MenuItem>
            <MenuItem value="BEAR">BEAR</MenuItem>
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void save()} disabled={saving || !name.trim()}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

function StrategyNewVersionDialog({
  open,
  strategy,
  onClose,
  onCreated,
}: {
  open: boolean
  strategy: SignalStrategy | null
  onClose: () => void
  onCreated: () => void
}) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<SignalStrategyVersionDraft>({
    enabled: true,
    inputs: [],
    variables: [],
    outputs: [],
  })

  useEffect(() => {
    if (!open) return
    setSaving(false)
    setError(null)
    setDraft(makeDraftFromVersion(strategy?.latest ?? null))
  }, [open, strategy])

  const save = async () => {
    if (!strategy) return
    setSaving(true)
    setError(null)
    try {
      const cleaned = sanitizeVersionDraft(draft)
      await createSignalStrategyVersion(strategy.id, cleaned)
      onCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create version')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>New version: {strategy?.name ?? ''}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {error && <Typography color="error">{error}</Typography>}
          <StrategyVersionEditor draft={draft} onChange={setDraft} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void save()} disabled={saving}>
          {saving ? 'Saving…' : 'Create version'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

function ImportDialog({
  open,
  onClose,
  onImported,
}: {
  open: boolean
  onClose: () => void
  onImported: () => void
}) {
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [fileText, setFileText] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setReplaceExisting(false)
    setFileText('')
    setError(null)
    setSaving(false)
  }, [open])

  const handleFile = async (file: File | null) => {
    if (!file) return
    setError(null)
    try {
      const text = await file.text()
      setFileText(text)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read file')
    }
  }

  const doImport = async () => {
    setSaving(true)
    setError(null)
    try {
      const parsed = JSON.parse(fileText) as Record<string, unknown>
      await importSignalStrategy({ payload: parsed, replace_existing: replaceExisting })
      onImported()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Import strategy</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {error && <Typography color="error">{error}</Typography>}
          <Button variant="outlined" component="label">
            Choose JSON file…
            <input
              type="file"
              accept="application/json"
              hidden
              onChange={(e) => void handleFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          <FormControlLabel
            control={
              <Switch
                checked={replaceExisting}
                onChange={(e) => setReplaceExisting(e.target.checked)}
              />
            }
            label="Replace existing strategy with same name (only if not used)"
          />
          <TextField
            label="Payload (JSON)"
            value={fileText}
            onChange={(e) => setFileText(e.target.value)}
            multiline
            minRows={8}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void doImport()} disabled={saving || !fileText.trim()}>
          {saving ? 'Importing…' : 'Import'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export function SignalStrategiesTab({ onError }: { onError?: (msg: string) => void }) {
  const [rows, setRows] = useState<SignalStrategy[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [editingMeta, setEditingMeta] = useState<SignalStrategy | null>(null)
  const [metaOpen, setMetaOpen] = useState(false)
  const [newVersionOpen, setNewVersionOpen] = useState(false)
  const [activeStrategy, setActiveStrategy] = useState<SignalStrategy | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await listSignalStrategies({ includeLatest: true, includeUsage: true })
      setRows(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load strategies')
      if (onError) onError(err instanceof Error ? err.message : 'Failed to load strategies')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const columns = useMemo<Array<GridColDef<SignalStrategy>>>(() => {
    return [
      { field: 'id', headerName: 'ID', width: 80 },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 220 },
      { field: 'scope', headerName: 'Scope', width: 110 },
      {
        field: 'latest_version',
        headerName: 'Latest',
        width: 100,
        valueGetter: (_value, row: SignalStrategy) => `v${row.latest_version}`,
      },
      {
        field: 'tags',
        headerName: 'Tags',
        flex: 1,
        minWidth: 180,
        renderCell: (p: GridRenderCellParams<SignalStrategy>) => (
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', py: 0.5 }}>
            {(p.row.tags ?? []).slice(0, 4).map((t) => (
              <Chip key={t} size="small" label={t} />
            ))}
            {(p.row.tags ?? []).length > 4 && (
              <Chip size="small" label={`+${(p.row.tags ?? []).length - 4}`} />
            )}
          </Box>
        ),
      },
      {
        field: 'regimes',
        headerName: 'Regimes',
        width: 150,
        valueGetter: (_value, row: SignalStrategy) => (row.regimes ?? []).join(', ') || '—',
      },
      {
        field: 'used_by',
        headerName: 'Used by',
        width: 160,
        valueGetter: (_value, row: SignalStrategy) =>
          `A:${row.used_by_alerts ?? 0} / S:${row.used_by_screeners ?? 0}`,
      },
      {
        field: 'updated_at',
        headerName: 'Updated',
        width: 190,
        valueGetter: (_value, row: SignalStrategy) => row.updated_at,
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 420,
        sortable: false,
        filterable: false,
        renderCell: (p: GridRenderCellParams<SignalStrategy>) => (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              onClick={() => {
                setEditingMeta(p.row)
                setMetaOpen(true)
              }}
            >
              Edit
            </Button>
            <Button
              size="small"
              onClick={() => {
                setActiveStrategy(p.row)
                setNewVersionOpen(true)
              }}
            >
              New version
            </Button>
            <Button
              size="small"
              onClick={async () => {
                try {
                  const exp = await exportSignalStrategy(p.row.id)
                  downloadJson(`${p.row.name}-strategy.json`, exp)
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Export failed')
                }
              }}
            >
              Export
            </Button>
            <Button
              size="small"
              onClick={async () => {
                try {
                  const versions = await listSignalStrategyVersions(p.row.id)
                  downloadJson(`${p.row.name}-versions.json`, versions)
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed to load versions')
                }
              }}
            >
              Versions
            </Button>
            <Button
              size="small"
              color="error"
              onClick={async () => {
                const ok = window.confirm(
                  `Delete strategy '${p.row.name}'? (blocked if in use)`,
                )
                if (!ok) return
                try {
                  await deleteSignalStrategy(p.row.id)
                  await refresh()
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Delete failed')
                }
              }}
            >
              Delete
            </Button>
          </Stack>
        ),
      },
    ]
  }, [])

  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Saved DSL V3 strategies with versioning, parameters, and multiple outputs. Use SIGNAL outputs in alerts/screener, and OVERLAY outputs in dashboard.
      </Typography>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <Button variant="contained" onClick={() => setCreateOpen(true)}>
          Create strategy
        </Button>
        <Button variant="outlined" onClick={() => setImportOpen(true)}>
          Import
        </Button>
        <Button variant="outlined" onClick={() => void refresh()} disabled={loading}>
          Refresh
        </Button>
      </Stack>
      <Paper sx={{ height: 560, width: '100%' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          density="compact"
          loading={loading}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
        />
      </Paper>

      <StrategyCreateDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={refresh} />
      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} onImported={refresh} />

      <StrategyMetadataDialog
        open={metaOpen}
        strategy={editingMeta}
        onClose={() => setMetaOpen(false)}
        onUpdated={refresh}
      />
      <StrategyNewVersionDialog
        open={newVersionOpen}
        strategy={activeStrategy}
        onClose={() => setNewVersionOpen(false)}
        onCreated={refresh}
      />
    </Box>
  )
}
