import FileDownloadIcon from '@mui/icons-material/FileDownload'
import FileUploadIcon from '@mui/icons-material/FileUpload'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Paper from '@mui/material/Paper'
import Snackbar from '@mui/material/Snackbar'
import Typography from '@mui/material/Typography'
import { useMemo, useRef, useState } from 'react'

import {
  exportRiskSettingsBundle,
  importRiskSettingsBundle,
  type RiskSettingsBundleV1,
} from '../services/riskBackup'

function fmtTs(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

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

export function RiskSettingsBackupPanel() {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [exporting, setExporting] = useState(false)
  const [lastExport, setLastExport] = useState<RiskSettingsBundleV1 | null>(null)

  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importFileName, setImportFileName] = useState<string | null>(null)
  const [importPayload, setImportPayload] = useState<RiskSettingsBundleV1 | null>(null)

  const [snack, setSnack] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const importSummary = useMemo(() => {
    if (!importPayload) return null
    return {
      schema_version: importPayload.schema_version,
      exported_at: importPayload.exported_at ?? null,
      exported_by: importPayload.exported_by ?? null,
      warnings: importPayload.warnings ?? [],
      counts: importPayload.counts ?? {},
    }
  }, [importPayload])

  const importHasEmptyUserCategories = useMemo(() => {
    if (!importPayload) return false
    const v = importPayload.symbol_categories_user
    return !Array.isArray(v) || v.length === 0
  }, [importPayload])

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Risk settings backup
        </Typography>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          style={{ display: 'none' }}
          onChange={async (e) => {
            const file = e.target.files?.[0] ?? null
            if (!file) return
            setImportFileName(file.name)
            setImportError(null)
            try {
              const text = await file.text()
              const parsed = JSON.parse(text) as RiskSettingsBundleV1
              setImportPayload(parsed)
              setImportOpen(true)
            } catch (err) {
              setImportPayload(null)
              setImportOpen(false)
              setImportError(err instanceof Error ? err.message : 'Failed to read JSON file')
            } finally {
              e.target.value = ''
            }
          }}
        />

        <Button
          size="small"
          variant="outlined"
          startIcon={<FileDownloadIcon />}
          disabled={exporting}
          onClick={async () => {
            setExporting(true)
            try {
              const data = await exportRiskSettingsBundle()
              setLastExport(data)
              const ts = fmtTs(new Date())
              downloadJson(`sigmatrader-risk-settings-${ts}.json`, data)
              setSnack(
                `Exported JSON (${data.counts ? Object.entries(data.counts).map(([k, v]) => `${k}=${v}`).join(', ') : 'ok'})`,
              )
            } catch (err) {
              setImportError(err instanceof Error ? err.message : 'Failed to export risk settings')
            } finally {
              setExporting(false)
            }
          }}
        >
          {exporting ? 'Exporting…' : 'Export JSON'}
        </Button>

        <Button
          size="small"
          variant="contained"
          startIcon={<FileUploadIcon />}
          disabled={importing}
          onClick={() => fileInputRef.current?.click()}
        >
          Import JSON
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        Export/import the entire risk settings state (replace-all). Export is read-only; it does not change your settings.
      </Typography>

      {lastExport?.warnings?.length ? (
        <Alert severity="warning" sx={{ mt: 1.5 }}>
          {lastExport.warnings.join(' ')}
        </Alert>
      ) : null}

      {importError ? (
        <Alert severity="error" sx={{ mt: 1.5 }}>
          {importError}
        </Alert>
      ) : null}

      <Dialog open={importOpen} onClose={() => (importing ? null : setImportOpen(false))} maxWidth="sm" fullWidth>
        <DialogTitle>Import risk settings JSON</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This will <b>replace all</b> existing risk settings (globals, profiles, thresholds, source overrides,
            symbol categories, holdings exit automation config).
          </Alert>

          <Typography variant="body2" sx={{ mb: 1 }}>
            File: {importFileName ?? '—'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Schema: {importSummary?.schema_version ?? '—'}
            {importSummary?.exported_at ? ` • Exported: ${importSummary.exported_at}` : ''}
            {importSummary?.exported_by ? ` • By: ${importSummary.exported_by}` : ''}
          </Typography>

          {importSummary?.warnings?.length ? (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {importSummary.warnings.join(' ')}
            </Alert>
          ) : null}

          {importHasEmptyUserCategories ? (
            <Alert severity="warning" sx={{ mt: 2 }}>
              This file contains <b>0</b> user symbol-category mappings. Importing will likely wipe your “Default category for new symbols” and per-symbol category mappings.
            </Alert>
          ) : null}

          {importError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {importError}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions sx={{ justifyContent: 'space-between' }}>
          <Button disabled={importing} onClick={() => setImportOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={importing || !importPayload}
            onClick={async () => {
              if (!importPayload) return
              const ok = window.confirm(
                'Replace all existing risk settings with this JSON?\n\nThis cannot be undone (unless you exported a backup).',
              )
              if (!ok) return
              let force = false
              if (importHasEmptyUserCategories) {
                const confirmEmpty = window.confirm(
                  'This JSON has 0 user symbol-category mappings.\n\nProceed anyway (this may wipe your symbol-category defaults/mappings)?',
                )
                if (!confirmEmpty) return
                force = true
              }
              setImporting(true)
              setImportError(null)
              try {
                const res = await importRiskSettingsBundle(importPayload, { force })
                setSnack(
                  res.ok
                    ? `Imported risk settings (${Object.entries(res.counts)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(', ')})`
                    : 'Import finished',
                )
                setImportOpen(false)
                setImportPayload(null)
                // Ensure all panels reflect the new server state.
                window.location.reload()
              } catch (err) {
                setImportError(err instanceof Error ? err.message : 'Failed to import risk settings')
              } finally {
                setImporting(false)
              }
            }}
          >
            {importing ? 'Importing…' : 'Replace & import'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={Boolean(snack)}
        autoHideDuration={2500}
        onClose={() => setSnack(null)}
        message={snack ?? ''}
      />
    </Paper>
  )
}
