import { useEffect, useMemo, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Divider from '@mui/material/Divider'

import {
  createGoalImportPreset,
  deleteGoalImportPreset,
  fetchGoalImportPresets,
  importHoldingGoals,
  type GoalLabel,
  type GoalTargetType,
  type HoldingGoalImportMapping,
  type HoldingGoalImportPreset,
  type HoldingGoalImportResult,
} from '../services/holdingsGoals'

const GOAL_LABELS: GoalLabel[] = [
  'CORE',
  'TRADE',
  'THEME',
  'HEDGE',
  'INCOME',
  'PARKING',
]

const GOAL_TARGET_TYPES: Array<{ value: GoalTargetType; label: string }> = [
  { value: 'PCT_FROM_AVG_BUY', label: '% from Avg Buy' },
  { value: 'PCT_FROM_LTP', label: '% from LTP' },
  { value: 'ABSOLUTE_PRICE', label: 'Absolute Price' },
]

type ParsedCsv = {
  headers: string[]
  rows: Array<Record<string, string>>
}

type Step = 'upload' | 'mapping' | 'summary'

type GoalImportDialogProps = {
  open: boolean
  brokerName: string
  holdingsSymbols: string[]
  onClose: () => void
  onImported: () => void
}

function parseCsv(text: string): ParsedCsv {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false

  const pushField = () => {
    row.push(field)
    field = ''
  }
  const pushRow = () => {
    if (row.length > 0 || field.length > 0) {
      pushField()
      rows.push(row)
    }
    row = []
  }

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    const next = text[i + 1]
    if (ch === '"') {
      if (inQuotes && next === '"') {
        field += '"'
        i += 1
      } else {
        inQuotes = !inQuotes
      }
      continue
    }
    if (!inQuotes && (ch === '\n' || ch === '\r')) {
      if (ch === '\r' && next === '\n') i += 1
      pushRow()
      continue
    }
    if (!inQuotes && ch === ',') {
      pushField()
      continue
    }
    field += ch
  }
  if (field.length || row.length) {
    pushRow()
  }

  const [headerRow, ...dataRows] = rows
  const headers = (headerRow || []).map((h) => h.trim()).filter(Boolean)
  const mappedRows = dataRows
    .filter((r) => r.some((cell) => String(cell ?? '').trim() !== ''))
    .map((r) => {
      const obj: Record<string, string> = {}
      headers.forEach((h, idx) => {
        obj[h] = String(r[idx] ?? '').trim()
      })
      return obj
    })

  return { headers, rows: mappedRows }
}

export function GoalImportDialog({
  open,
  brokerName,
  holdingsSymbols,
  onClose,
  onImported,
}: GoalImportDialogProps) {
  const [step, setStep] = useState<Step>('upload')
  const [parsed, setParsed] = useState<ParsedCsv | null>(null)
  const [mapping, setMapping] = useState<HoldingGoalImportMapping>({
    symbol_column: '',
    exchange_column: null,
    label_column: null,
    label_default: 'CORE',
    review_date_column: null,
    review_date_default_days: 90,
    target_value_column: null,
    target_type: null,
    note_column: null,
  })
  const [presets, setPresets] = useState<HoldingGoalImportPreset[]>([])
  const [selectedPresetId, setSelectedPresetId] = useState<number | ''>('')
  const [presetName, setPresetName] = useState('')
  const [importResult, setImportResult] = useState<HoldingGoalImportResult | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setStep('upload')
    setParsed(null)
    setImportResult(null)
    setError(null)
    setSelectedPresetId('')
    setPresetName('')
    setMapping((prev) => ({
      ...prev,
      symbol_column: '',
    }))
    void (async () => {
      try {
        const res = await fetchGoalImportPresets()
        setPresets(res)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load presets.')
      }
    })()
  }, [open])

  const previewRows = useMemo(() => {
    if (!parsed) return []
    return parsed.rows.slice(0, 10)
  }, [parsed])

  const handleFile = async (file: File) => {
    setError(null)
    setBusy(true)
    try {
      const text = await file.text()
      const parsedCsv = parseCsv(text)
      if (!parsedCsv.headers.length) {
        setError('CSV must include a header row.')
        return
      }
      setParsed(parsedCsv)
      setStep('mapping')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to parse CSV.')
    } finally {
      setBusy(false)
    }
  }

  const handleImport = async () => {
    if (!parsed) return
    if (!mapping.symbol_column) {
      setError('Select a symbol column to continue.')
      return
    }
    if (mapping.target_value_column && !mapping.target_type) {
      setError('Select a target type for the target column.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await importHoldingGoals({
        broker_name: brokerName,
        mapping,
        rows: parsed.rows,
        holdings_symbols: holdingsSymbols,
      })
      setImportResult(result)
      setStep('summary')
      onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleSavePreset = async () => {
    if (!presetName.trim()) {
      setError('Preset name is required.')
      return
    }
    try {
      const preset = await createGoalImportPreset({
        name: presetName.trim(),
        mapping,
      })
      setPresets((prev) => [...prev, preset].sort((a, b) => a.name.localeCompare(b.name)))
      setPresetName('')
      setSelectedPresetId(preset.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save preset.')
    }
  }

  const handlePresetSelect = (id: number | '') => {
    setSelectedPresetId(id)
    if (id === '') return
    const preset = presets.find((p) => p.id === id)
    if (preset) {
      setMapping({ ...preset.mapping })
    }
  }

  const handleDeletePreset = async () => {
    if (selectedPresetId === '') return
    try {
      await deleteGoalImportPreset(selectedPresetId)
      setPresets((prev) => prev.filter((p) => p.id !== selectedPresetId))
      setSelectedPresetId('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete preset.')
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Import Goals CSV</DialogTitle>
      <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {error && (
          <Typography variant="caption" color="error">
            {error}
          </Typography>
        )}

        {step === 'upload' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Upload a CSV file to map holdings goals. We will preview the first 10 rows.
            </Typography>
            <Button variant="outlined" component="label" disabled={busy}>
              Choose CSV
              <input
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void handleFile(file)
                }}
              />
            </Button>
          </Box>
        )}

        {step === 'mapping' && parsed && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="subtitle2">Preview</Typography>
            <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, overflow: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {parsed.headers.map((h) => (
                      <TableCell key={h}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {previewRows.map((row, idx) => (
                    <TableRow key={idx}>
                      {parsed.headers.map((h) => (
                        <TableCell key={h}>{row[h]}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>

            <Divider />

            <Typography variant="subtitle2">Column mapping</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
              <TextField
                select
                label="Symbol column"
                value={mapping.symbol_column}
                onChange={(e) =>
                  setMapping((prev) => ({ ...prev, symbol_column: e.target.value }))
                }
              >
                <MenuItem value="">Select column</MenuItem>
                {parsed.headers.map((h) => (
                  <MenuItem key={h} value={h}>
                    {h}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Exchange column (optional)"
                value={mapping.exchange_column ?? ''}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    exchange_column: e.target.value || null,
                  }))
                }
              >
                <MenuItem value="">None</MenuItem>
                {parsed.headers.map((h) => (
                  <MenuItem key={h} value={h}>
                    {h}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Label column (optional)"
                value={mapping.label_column ?? ''}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    label_column: e.target.value || null,
                  }))
                }
              >
                <MenuItem value="">None</MenuItem>
                {parsed.headers.map((h) => (
                  <MenuItem key={h} value={h}>
                    {h}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Default label"
                value={mapping.label_default ?? 'CORE'}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    label_default: e.target.value as GoalLabel,
                  }))
                }
              >
                {GOAL_LABELS.map((label) => (
                  <MenuItem key={label} value={label}>
                    {label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Review date column (optional)"
                value={mapping.review_date_column ?? ''}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    review_date_column: e.target.value || null,
                  }))
                }
              >
                <MenuItem value="">None</MenuItem>
                {parsed.headers.map((h) => (
                  <MenuItem key={h} value={h}>
                    {h}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Default review days"
                type="number"
                value={mapping.review_date_default_days ?? 90}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    review_date_default_days: Number(e.target.value) || null,
                  }))
                }
              />
              <TextField
                select
                label="Target value column (optional)"
                value={mapping.target_value_column ?? ''}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    target_value_column: e.target.value || null,
                  }))
                }
              >
                <MenuItem value="">None</MenuItem>
                {parsed.headers.map((h) => (
                  <MenuItem key={h} value={h}>
                    {h}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Target type"
                value={mapping.target_type ?? ''}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    target_type: (e.target.value as GoalTargetType) || null,
                  }))
                }
                disabled={!mapping.target_value_column}
              >
                <MenuItem value="">None</MenuItem>
                {GOAL_TARGET_TYPES.map((opt) => (
                  <MenuItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Note column (optional)"
                value={mapping.note_column ?? ''}
                onChange={(e) =>
                  setMapping((prev) => ({
                    ...prev,
                    note_column: e.target.value || null,
                  }))
                }
              >
                <MenuItem value="">None</MenuItem>
                {parsed.headers.map((h) => (
                  <MenuItem key={h} value={h}>
                    {h}
                  </MenuItem>
                ))}
              </TextField>
            </Box>

            <Divider />

            <Typography variant="subtitle2">Presets</Typography>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <Select
                size="small"
                value={selectedPresetId}
                onChange={(e) => handlePresetSelect(e.target.value as number | '')}
                displayEmpty
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="">Select preset</MenuItem>
                {presets.map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.name}
                  </MenuItem>
                ))}
              </Select>
              <Button
                size="small"
                variant="outlined"
                disabled={selectedPresetId === ''}
                onClick={handleDeletePreset}
              >
                Delete preset
              </Button>
              <TextField
                size="small"
                label="Preset name"
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
              />
              <Button size="small" variant="contained" onClick={handleSavePreset}>
                Save preset
              </Button>
            </Box>
          </Box>
        )}

        {step === 'summary' && importResult && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="subtitle2">Import summary</Typography>
            <Typography variant="body2">
              Matched: {importResult.matched} · Created: {importResult.created} ·
              Updated: {importResult.updated} · Skipped: {importResult.skipped}
            </Typography>
            {importResult.errors.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Errors (first 20):
                </Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Row</TableCell>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Reason</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {importResult.errors.slice(0, 20).map((err, idx) => (
                      <TableRow key={idx}>
                        <TableCell>{err.row_index}</TableCell>
                        <TableCell>{err.symbol ?? '—'}</TableCell>
                        <TableCell>{err.reason}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        {step === 'mapping' && (
          <Button variant="contained" onClick={handleImport} disabled={busy}>
            Import
          </Button>
        )}
      </DialogActions>
    </Dialog>
  )
}
