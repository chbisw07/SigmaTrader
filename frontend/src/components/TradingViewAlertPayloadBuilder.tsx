import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import Snackbar from '@mui/material/Snackbar'
import Switch from '@mui/material/Switch'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Alert from '@mui/material/Alert'
import { useEffect, useMemo, useState } from 'react'

import {
  deleteTradingViewAlertPayloadTemplate,
  fetchTradingViewAlertPayloadTemplate,
  listTradingViewAlertPayloadTemplates,
  upsertTradingViewAlertPayloadTemplate,
  type TradingViewAlertPayloadBuilderConfigV1,
  type TradingViewAlertPayloadTemplateSummary,
  type TradingViewHintFieldV1,
} from '../services/tradingviewAlertPayloadTemplates'

type RawToken = { __raw: string }

export type SignalFields = {
  strategy_id: string
  strategy_name: string
  symbol: string
  exchange: string
  side: string
  price: string
  timeframe: string
  timestamp: string
  order_id: string
}

export const DEFAULT_SIGNAL: SignalFields = {
  strategy_id: 'DUAL_MA_VOL_REENTRY_V1',
  strategy_name: 'Dual MA + Volatility-Adaptive Exits + Trend Re-entry',
  symbol: '{{ticker}}',
  exchange: '{{exchange}}',
  side: '{{strategy.order.action}}',
  price: '{{close}}',
  timeframe: '{{interval}}',
  timestamp: '{{timenow}}',
  order_id: '{{strategy.order.id}}',
}

export const DEFAULT_SIGNAL_ENABLED: Record<keyof SignalFields, boolean> = {
  strategy_id: true,
  strategy_name: true,
  symbol: true,
  exchange: true,
  side: true,
  price: true,
  timeframe: true,
  timestamp: true,
  order_id: true,
}

const OPTIONAL_SIGNAL_KEYS = new Set<keyof SignalFields>([
  'strategy_name',
  'exchange',
  'order_id',
])

const HINT_KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/
const RAW_TOKEN_RE = /^\{\{[A-Za-z0-9_.]+\}\}$/

function isRawToken(value: string): boolean {
  return RAW_TOKEN_RE.test(value.trim())
}

function stringifyJsonWithRawTokens(value: any, indent = 2): string {
  const pad = (n: number) => ' '.repeat(n)

  const render = (v: any, depth: number): string => {
    if (v && typeof v === 'object' && '__raw' in v) {
      return String((v as RawToken).__raw)
    }
    if (v === null) return 'null'
    if (typeof v === 'string') return JSON.stringify(v)
    if (typeof v === 'number' || typeof v === 'boolean') return String(v)
    if (Array.isArray(v)) {
      if (v.length === 0) return '[]'
      const inner = v
        .map((item) => `${pad(depth + indent)}${render(item, depth + indent)}`)
        .join(',\n')
      return `[\n${inner}\n${pad(depth)}]`
    }
    if (v && typeof v === 'object') {
      const entries = Object.entries(v)
      if (entries.length === 0) return '{}'
      const inner = entries
        .map(([k, val]) => {
          return `${pad(depth + indent)}${JSON.stringify(k)}: ${render(
            val,
            depth + indent,
          )}`
        })
        .join(',\n')
      return `{\n${inner}\n${pad(depth)}}`
    }
    return JSON.stringify(String(v))
  }

  return render(value, 0)
}

function toNumberOrRawToken(value: string): number | RawToken | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  if (isRawToken(trimmed)) return { __raw: trimmed }
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return null
  return n
}

export function buildTradingViewAlertPayloadJson(args: {
  secret: string
  maskSecret: boolean
  signal: SignalFields
  signalEnabled: Record<string, boolean>
  hints: TradingViewHintFieldV1[]
}): string {
  const signalObj: Record<string, any> = {}
  ;(Object.keys(args.signal) as (keyof SignalFields)[]).forEach((key) => {
    if (!args.signalEnabled[key]) return
    if (key === 'price') {
      const v = toNumberOrRawToken(args.signal.price)
      signalObj.price = v ?? args.signal.price
    } else {
      signalObj[key] = (args.signal as any)[key]
    }
  })

  const hintsObj: Record<string, any> = {}
  args.hints.forEach((h) => {
    const key = (h.key || '').trim()
    if (!key) return

    if (h.type === 'number') {
      const v = toNumberOrRawToken(String(h.value ?? ''))
      hintsObj[key] = v ?? String(h.value ?? '')
      return
    }
    if (h.type === 'boolean') {
      hintsObj[key] = Boolean(h.value)
      return
    }
    if (h.type === 'enum') {
      hintsObj[key] = String(h.value ?? '')
      return
    }
    hintsObj[key] = String(h.value ?? '')
  })

  const obj = {
    meta: {
      secret: args.maskSecret ? '********' : args.secret,
      platform: 'TRADINGVIEW',
      version: '1.0',
    },
    signal: signalObj,
    hints: hintsObj,
  }

  return stringifyJsonWithRawTokens(obj, 2)
}

function normalizeEnumOptions(raw: string): string[] {
  return raw
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
}

async function writeToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const el = document.createElement('textarea')
  el.value = text
  el.style.position = 'fixed'
  el.style.left = '-1000px'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

export function TradingViewAlertPayloadBuilder({
  webhookSecret,
}: {
  webhookSecret: string
}) {
  const effectiveSecret = webhookSecret?.trim() ? webhookSecret.trim() : '{{SECRET}}'
  const recommendedAlertMessage = '{{strategy.order.alert_message}}'

  const [templateName, setTemplateName] = useState<string>('')
  const [signal, setSignal] = useState<SignalFields>(() => ({ ...DEFAULT_SIGNAL }))
  const [signalEnabled, setSignalEnabled] = useState<Record<string, boolean>>(() => ({
    ...DEFAULT_SIGNAL_ENABLED,
  }))
  const [hints, setHints] = useState<TradingViewHintFieldV1[]>([])

  const [snackbar, setSnackbar] = useState<{
    open: boolean
    message: string
    severity: 'success' | 'error' | 'info'
  }>({ open: false, message: '', severity: 'info' })

  const [loadOpen, setLoadOpen] = useState(false)
  const [templates, setTemplates] = useState<TradingViewAlertPayloadTemplateSummary[]>([])
  const [loadBusy, setLoadBusy] = useState(false)

  const hintKeyErrors = useMemo(() => {
    const errors: Record<number, string> = {}
    const seen = new Map<string, number>()
    hints.forEach((h, idx) => {
      const key = (h.key || '').trim()
      if (!key) {
        errors[idx] = 'Key is required.'
        return
      }
      if (!HINT_KEY_RE.test(key)) {
        errors[idx] = 'Key must match ^[A-Za-z_][A-Za-z0-9_]*$'
        return
      }
      const prev = seen.get(key)
      if (typeof prev === 'number') {
        errors[idx] = 'Key must be unique.'
        errors[prev] = 'Key must be unique.'
        return
      }
      seen.set(key, idx)
    })
    return errors
  }, [hints])

  const hintValueErrors = useMemo(() => {
    const errors: Record<number, string> = {}
    hints.forEach((h, idx) => {
      if (h.type === 'number') {
        if (toNumberOrRawToken(String(h.value ?? '')) === null) {
          errors[idx] = 'Number must be a numeric value or a token like {{close}}.'
        }
      }
      if (h.type === 'enum') {
        const options = Array.isArray(h.enum_options) ? h.enum_options : []
        if (options.length === 0) {
          errors[idx] = 'Enum options are required.'
        } else if (typeof h.value !== 'string' || !options.includes(h.value)) {
          errors[idx] = 'Enum value must be one of the options.'
        }
      }
    })
    return errors
  }, [hints])

  const signalErrors = useMemo(() => {
    const errors: Partial<Record<keyof SignalFields, string>> = {}
    ;(Object.keys(DEFAULT_SIGNAL) as (keyof SignalFields)[]).forEach((key) => {
      if (!signalEnabled[key]) return
      const raw = String((signal as any)[key] ?? '').trim()
      if (!raw) {
        errors[key] = 'Required.'
        return
      }
      if (key === 'price' && toNumberOrRawToken(raw) === null) {
        errors.price = 'Must be a number or a token like {{close}}.'
      }
    })
    return errors
  }, [signal, signalEnabled])

  const builderConfig: TradingViewAlertPayloadBuilderConfigV1 = useMemo(() => {
    return {
      version: '1.0',
      signal,
      signal_enabled: signalEnabled,
      hints,
    }
  }, [signal, signalEnabled, hints])

  const payloadPreview = useMemo(() => {
    return buildTradingViewAlertPayloadJson({
      secret: effectiveSecret,
      maskSecret: true,
      signal,
      signalEnabled,
      hints,
    })
  }, [signal, signalEnabled, hints, effectiveSecret])

  const payloadForCopy = useMemo(() => {
    return buildTradingViewAlertPayloadJson({
      secret: effectiveSecret,
      maskSecret: false,
      signal,
      signalEnabled,
      hints,
    })
  }, [signal, signalEnabled, hints, effectiveSecret])

  const hasErrors =
    Object.keys(hintKeyErrors).length > 0 ||
    Object.keys(hintValueErrors).length > 0 ||
    Object.keys(signalErrors).length > 0

  const loadTemplates = async () => {
    setLoadBusy(true)
    try {
      const data = await listTradingViewAlertPayloadTemplates()
      setTemplates(data)
    } catch (err) {
      setSnackbar({
        open: true,
        message: err instanceof Error ? err.message : 'Failed to load templates',
        severity: 'error',
      })
    } finally {
      setLoadBusy(false)
    }
  }

  useEffect(() => {
    if (!loadOpen) return
    void loadTemplates()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadOpen])

  const reset = () => {
    setTemplateName('')
    setSignal({ ...DEFAULT_SIGNAL })
    setSignalEnabled({ ...DEFAULT_SIGNAL_ENABLED })
    setHints([])
    setSnackbar({ open: true, message: 'Reset to defaults.', severity: 'info' })
  }

  const addHint = () => {
    setHints((prev) => [
      ...prev,
      { key: '', type: 'string', value: '', enum_options: undefined },
    ])
  }

  const updateHint = (idx: number, patch: Partial<TradingViewHintFieldV1>) => {
    setHints((prev) => prev.map((h, i) => (i === idx ? { ...h, ...patch } : h)))
  }

  const removeHint = (idx: number) => {
    setHints((prev) => prev.filter((_, i) => i !== idx))
  }

  const isRiskyHintKey = (key: string): boolean => {
    const k = key.toLowerCase()
    return (
      k.includes('qty') ||
      k.includes('quantity') ||
      k.includes('risk') ||
      k.includes('drawdown') ||
      k.includes('leverage') ||
      k.includes('stop')
    )
  }

  const saveTemplate = async () => {
    const name = templateName.trim()
    if (!name) {
      setSnackbar({ open: true, message: 'Template name is required.', severity: 'error' })
      return
    }
    try {
      await upsertTradingViewAlertPayloadTemplate({ name, config: builderConfig })
      setSnackbar({ open: true, message: `Saved template: ${name}`, severity: 'success' })
      await loadTemplates()
    } catch (err) {
      setSnackbar({
        open: true,
        message: err instanceof Error ? err.message : 'Failed to save template',
        severity: 'error',
      })
    }
  }

  const loadTemplate = async (id: number) => {
    setLoadBusy(true)
    try {
      const tpl = await fetchTradingViewAlertPayloadTemplate(id)
      setTemplateName(tpl.name)
      setSignal({ ...DEFAULT_SIGNAL, ...(tpl.config.signal as any) })
      setSignalEnabled({ ...DEFAULT_SIGNAL_ENABLED, ...(tpl.config.signal_enabled as any) })
      setHints(Array.isArray(tpl.config.hints) ? tpl.config.hints : [])
      setSnackbar({ open: true, message: `Loaded template: ${tpl.name}`, severity: 'success' })
      setLoadOpen(false)
    } catch (err) {
      setSnackbar({
        open: true,
        message: err instanceof Error ? err.message : 'Failed to load template',
        severity: 'error',
      })
    } finally {
      setLoadBusy(false)
    }
  }

  const deleteTemplate = async (id: number, name: string) => {
    const confirmed = window.confirm(`Delete template "${name}"?`)
    if (!confirmed) return
    setLoadBusy(true)
    try {
      await deleteTradingViewAlertPayloadTemplate(id)
      setTemplates((prev) => prev.filter((x) => x.id !== id))
      setSnackbar({ open: true, message: `Deleted template: ${name}`, severity: 'info' })
    } catch (err) {
      setSnackbar({
        open: true,
        message: err instanceof Error ? err.message : 'Failed to delete template',
        severity: 'error',
      })
    } finally {
      setLoadBusy(false)
    }
  }

  const onCopy = async () => {
    if (hasErrors) {
      setSnackbar({
        open: true,
        message: 'Fix validation errors before copying.',
        severity: 'error',
      })
      return
    }
    try {
      await writeToClipboard(payloadForCopy)
      setSnackbar({ open: true, message: 'Copied JSON to clipboard.', severity: 'success' })
    } catch (err) {
      setSnackbar({
        open: true,
        message: err instanceof Error ? err.message : 'Failed to copy JSON',
        severity: 'error',
      })
    }
  }

  const onCopyRecommendedMessage = async () => {
    try {
      await writeToClipboard(recommendedAlertMessage)
      setSnackbar({
        open: true,
        message: 'Copied TradingView alert message.',
        severity: 'success',
      })
    } catch (err) {
      setSnackbar({
        open: true,
        message: err instanceof Error ? err.message : 'Failed to copy message',
        severity: 'error',
      })
    }
  }

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Alert Payload Builder
        </Typography>
        <Button
          size="small"
          variant="contained"
          startIcon={<ContentCopyIcon />}
          onClick={() => void onCopy()}
          disabled={hasErrors}
        >
          Copy JSON
        </Button>
        <Button size="small" variant="outlined" onClick={reset}>
          Reset
        </Button>
        <Button size="small" variant="outlined" onClick={() => void saveTemplate()}>
          Save Template
        </Button>
        <Button size="small" variant="outlined" onClick={() => setLoadOpen(true)}>
          Load Template
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
        This builder produces signals (not executable orders). Hints are informational only and may
        be ignored by SigmaTrader.
      </Typography>

      <Alert severity="info" sx={{ mt: 1 }}>
        <Typography variant="body2" sx={{ mb: 1 }}>
          Recommended for SigmaTrader TradingView Strategy v6: create a single TradingView alert
          (Strategy → Order fills) and set Message to:
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            size="small"
            value={recommendedAlertMessage}
            label="TradingView alert message"
            fullWidth
            sx={{ maxWidth: 520 }}
            InputProps={{ readOnly: true }}
          />
          <Button
            size="small"
            variant="outlined"
            startIcon={<ContentCopyIcon />}
            onClick={() => void onCopyRecommendedMessage()}
          >
            Copy
          </Button>
        </Box>
      </Alert>

      <Divider sx={{ my: 2 }} />

      <TextField
        size="small"
        label="Template name"
        value={templateName}
        onChange={(e) => setTemplateName(e.target.value)}
        sx={{ maxWidth: 420, width: '100%' }}
      />

      <Divider sx={{ my: 2 }} />

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
          gap: 2,
          alignItems: 'start',
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              META (required, locked)
            </Typography>
            <TextField
              size="small"
              label="secret"
              value="********"
              disabled
              sx={{ mb: 1, width: '100%' }}
              helperText={
                webhookSecret?.trim()
                  ? 'Secret is masked here; Copy JSON uses the real secret.'
                  : 'Set the TradingView webhook secret above, or replace {{SECRET}} after copying.'
              }
            />
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <TextField size="small" label="platform" value="TRADINGVIEW" disabled />
              <TextField size="small" label="version" value="1.0" disabled />
            </Box>
          </Paper>

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              SIGNAL
            </Typography>

            {(Object.keys(DEFAULT_SIGNAL) as (keyof SignalFields)[]).map((key) => {
              const enabled = Boolean(signalEnabled[key])
              const optional = OPTIONAL_SIGNAL_KEYS.has(key)
              const err = (signalErrors as any)[key] as string | undefined
              return (
                <Box
                  key={key}
                  sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 1, flexWrap: 'wrap' }}
                >
                  {optional ? (
                    <FormControlLabel
                      control={
                        <Switch
                          size="small"
                          checked={enabled}
                          onChange={(e) =>
                            setSignalEnabled((prev) => ({
                              ...prev,
                              [key]: e.target.checked,
                            }))
                          }
                        />
                      }
                      label={key}
                      sx={{ minWidth: 190, mr: 0 }}
                    />
                  ) : (
                    <Typography variant="body2" sx={{ minWidth: 190 }}>
                      {key}
                    </Typography>
                  )}
                  {key === 'side' ? (
                    <TextField
                      select
                      size="small"
                      value={(signal as any)[key]}
                      disabled={!enabled}
                      onChange={(e) => setSignal((prev) => ({ ...prev, [key]: e.target.value }))}
                      sx={{ flex: 1, minWidth: 240 }}
                      error={Boolean(err)}
                      helperText={
                        err ||
                        'If you are not using a Strategy “Order fills” alert, {{strategy.order.action}} will not be expanded. Choose BUY/SELL.'
                      }
                    >
                      <MenuItem value="{{strategy.order.action}}">{'{{strategy.order.action}}'}</MenuItem>
                      <MenuItem value="BUY">BUY</MenuItem>
                      <MenuItem value="SELL">SELL</MenuItem>
                    </TextField>
                  ) : (
                    <TextField
                      size="small"
                      value={(signal as any)[key]}
                      disabled={!enabled}
                      onChange={(e) => setSignal((prev) => ({ ...prev, [key]: e.target.value }))}
                      sx={{ flex: 1, minWidth: 240 }}
                      error={Boolean(err)}
                      helperText={
                        err ||
                        (key === 'price'
                          ? 'Numeric field: use {{close}}-style tokens without quotes.'
                          : key === 'order_id'
                            ? 'Order id token works only for Strategy “Order fills” alerts.'
                            : ' ')
                      }
                    />
                  )}
                </Box>
              )
            })}
          </Paper>

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography variant="subtitle2" sx={{ flex: 1 }}>
                HINTS (optional, informational only)
              </Typography>
              <Button size="small" variant="outlined" onClick={addHint}>
                + Add Field
              </Button>
            </Box>

            <Typography variant="caption" color="warning.main" sx={{ display: 'block', mb: 1 }}>
              Hints do not control risk or execution.
            </Typography>

            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Key</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Value</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {hints.map((h, idx) => {
                  const keyErr = hintKeyErrors[idx]
                  const valErr = hintValueErrors[idx]
                  const risky = h.key ? isRiskyHintKey(h.key) : false
                  const enumOptions = Array.isArray(h.enum_options) ? h.enum_options : []
                  return (
                    <TableRow key={idx}>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        <TextField
                          size="small"
                          value={h.key}
                          onChange={(e) => updateHint(idx, { key: e.target.value })}
                          inputProps={{ 'aria-label': `hint-key-${idx}` }}
                          error={Boolean(keyErr)}
                          helperText={keyErr || (risky ? 'Looks like a risk/sizing key; treated as informational only.' : ' ')}
                        />
                      </TableCell>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        <FormControl size="small" sx={{ minWidth: 120 }}>
                          <InputLabel>Type</InputLabel>
                          <Select
                            label="Type"
                            value={h.type}
                            onChange={(e) => {
                              const nextType = e.target.value as TradingViewHintFieldV1['type']
                              if (nextType === 'boolean') {
                                updateHint(idx, { type: nextType, value: false, enum_options: undefined })
                                return
                              }
                              if (nextType === 'enum') {
                                updateHint(idx, { type: nextType, value: '', enum_options: [] })
                                return
                              }
                              updateHint(idx, { type: nextType, value: '', enum_options: undefined })
                            }}
                          >
                            <MenuItem value="string">string</MenuItem>
                            <MenuItem value="number">number</MenuItem>
                            <MenuItem value="boolean">boolean</MenuItem>
                            <MenuItem value="enum">enum</MenuItem>
                          </Select>
                        </FormControl>
                      </TableCell>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        {h.type === 'boolean' ? (
                          <FormControlLabel
                            control={
                              <Switch
                                size="small"
                                checked={Boolean(h.value)}
                                onChange={(e) => updateHint(idx, { value: e.target.checked })}
                              />
                            }
                            label={Boolean(h.value) ? 'true' : 'false'}
                          />
                        ) : h.type === 'enum' ? (
                          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                            <TextField
                              size="small"
                              label="Options (comma-separated)"
                              value={enumOptions.join(', ')}
                              onChange={(e) =>
                                updateHint(idx, { enum_options: normalizeEnumOptions(e.target.value) })
                              }
                              error={Boolean(valErr)}
                            />
                            <FormControl size="small">
                              <InputLabel>Value</InputLabel>
                              <Select
                                label="Value"
                                value={typeof h.value === 'string' ? h.value : ''}
                                onChange={(e) => updateHint(idx, { value: e.target.value })}
                                error={Boolean(valErr)}
                              >
                                {enumOptions.length === 0 ? (
                                  <MenuItem value="">(add options)</MenuItem>
                                ) : (
                                  enumOptions.map((opt) => (
                                    <MenuItem key={opt} value={opt}>
                                      {opt}
                                    </MenuItem>
                                  ))
                                )}
                              </Select>
                              {valErr ? (
                                <Typography variant="caption" color="error" sx={{ mt: 0.5 }}>
                                  {valErr}
                                </Typography>
                              ) : null}
                            </FormControl>
                          </Box>
                        ) : (
                          <TextField
                            size="small"
                            value={String(h.value ?? '')}
                            onChange={(e) => updateHint(idx, { value: e.target.value })}
                            error={Boolean(valErr)}
                            helperText={valErr || (h.type === 'number' ? 'Supports {{token}} (unquoted) or a number.' : ' ')}
                          />
                        )}
                      </TableCell>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        <IconButton size="small" onClick={() => removeHint(idx)} aria-label="Delete hint">
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {hints.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography variant="body2" color="text.secondary">
                        No hints yet.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </Paper>
        </Box>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Live JSON Preview (read-only)
          </Typography>
          <Box
            component="pre"
            sx={{
              m: 0,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              fontSize: 12,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: 560,
              overflow: 'auto',
              bgcolor: 'background.default',
              p: 1.5,
              borderRadius: 1,
            }}
            aria-label="json-preview"
          >
            {payloadPreview}
          </Box>
          {hasErrors ? (
            <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
              Fix validation errors to enable copying.
            </Typography>
          ) : null}
        </Paper>
      </Box>

      <Dialog open={loadOpen} onClose={() => setLoadOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Load Template</DialogTitle>
        <DialogContent>
          {templates.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {loadBusy ? 'Loading…' : 'No templates saved yet.'}
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {templates.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>{t.name}</TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={loadBusy}
                        onClick={() => void loadTemplate(t.id)}
                        sx={{ mr: 1 }}
                      >
                        Load
                      </Button>
                      <IconButton
                        size="small"
                        disabled={loadBusy}
                        onClick={() => void deleteTemplate(t.id, t.name)}
                        aria-label={`Delete template ${t.name}`}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </DialogContent>
        <DialogActions>
          <Button size="small" onClick={() => void loadTemplates()} disabled={loadBusy}>
            Refresh
          </Button>
          <Button size="small" onClick={() => setLoadOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={2400}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          severity={snackbar.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Paper>
  )
}
