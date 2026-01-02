import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'
import { useEffect, useMemo, useState } from 'react'

type PayloadRow = { id: string; key: string; value: string }

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

async function copyToClipboard(text: string): Promise<void> {
  const raw = String(text ?? '')
  try {
    await navigator.clipboard.writeText(raw)
    return
  } catch {
    // Fallback for environments without clipboard permissions.
  }

  const el = document.createElement('textarea')
  el.value = raw
  el.style.position = 'fixed'
  el.style.left = '-9999px'
  el.style.top = '0'
  document.body.appendChild(el)
  el.focus()
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

function safeStringify(value: unknown, pretty: boolean): string {
  try {
    return JSON.stringify(value, null, pretty ? 2 : 0) ?? ''
  } catch {
    return String(value ?? '')
  }
}

export function KeyValueJsonDialog({
  open,
  onClose,
  title,
  value,
}: {
  open: boolean
  onClose: () => void
  title: string
  value: unknown
}) {
  const [tab, setTab] = useState<'table' | 'json'>('table')
  const [pretty, setPretty] = useState(true)
  const [copiedLabel, setCopiedLabel] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setTab('table')
    setPretty(true)
    setCopiedLabel(null)
  }, [open])

  const rows = useMemo((): PayloadRow[] => {
    const flattened = flattenJson(value)
    return flattened.map((item) => ({
      id: item.key,
      key: item.key,
      value: formatValue(item.value),
    }))
  }, [value])

  const jsonText = useMemo(() => safeStringify(value, pretty), [pretty, value])

  const columns = useMemo((): GridColDef[] => {
    return [
      { field: 'key', headerName: 'Key', width: 300 },
      {
        field: 'value',
        headerName: 'Value',
        flex: 1,
        minWidth: 320,
        renderCell: (params) => {
          const v = String(params.value ?? '')
          const label = `Copy ${String(params.row.key ?? '')}`
          const copied = copiedLabel === label
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
              <Typography
                variant="body2"
                sx={{
                  flex: 1,
                  minWidth: 0,
                  userSelect: 'text',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {v}
              </Typography>
              <Tooltip title={copied ? 'Copied' : 'Copy'}>
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation()
                    void copyToClipboard(v).then(() => setCopiedLabel(label))
                  }}
                >
                  <ContentCopyIcon fontSize="inherit" />
                </IconButton>
              </Tooltip>
            </Box>
          )
        },
      },
    ]
  }, [copiedLabel])

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Tabs value={tab} onChange={(_e, v) => setTab(v as 'table' | 'json')} sx={{ mb: 1 }}>
          <Tab value="table" label="Table" />
          <Tab value="json" label="JSON" />
        </Tabs>
        <Divider sx={{ mb: 2 }} />
        {tab === 'table' ? (
          <Paper sx={{ height: 460 }}>
            <DataGrid
              rows={rows}
              columns={columns}
              getRowId={(row) => row.id}
              disableRowSelectionOnClick
              density="compact"
              sx={{ height: '100%' }}
              initialState={{
                pagination: { paginationModel: { pageSize: 100 } },
              }}
              pageSizeOptions={[25, 50, 100]}
            />
          </Paper>
        ) : (
          <>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1, gap: 1 }}>
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  void copyToClipboard(jsonText)
                  setCopiedLabel('Copy JSON')
                }}
              >
                Copy JSON
              </Button>
              <Button size="small" onClick={() => setPretty((v) => !v)}>
                {pretty ? 'Formatted' : 'Raw'}
              </Button>
            </Box>
            <TextField
              value={jsonText}
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
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}

