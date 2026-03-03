import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import {
  fetchUnifiedRiskGlobal,
  updateUnifiedRiskGlobal,
  type UnifiedRiskGlobal,
} from '../services/riskUnified'
import {
  clearUiPauseAutoRule,
  extractUiPauseAutoWindow,
  isValidHHMM,
  setUiPauseAutoRule,
} from '../utils/noTradeRulesUi'

function numOrZero(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function RiskGlobalsPanel() {
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<UnifiedRiskGlobal | null>(null)
  const [pauseStart, setPauseStart] = useState<string>('')
  const [pauseEnd, setPauseEnd] = useState<string>('')
  const [pauseInputError, setPauseInputError] = useState<string | null>(null)

  const nowIstHHMM = (): string => {
    try {
      const s = new Date().toLocaleTimeString('en-GB', {
        timeZone: 'Asia/Kolkata',
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
      })
      return isValidHHMM(s) ? s : ''
    } catch {
      return ''
    }
  }

  const addMinutesHHMM = (hhmm: string, minutes: number): string => {
    if (!isValidHHMM(hhmm)) return ''
    const [hh, mm] = hhmm.split(':').map((x) => Number(x))
    const total = (hh * 60 + mm + minutes) % (24 * 60)
    const outH = Math.floor(total / 60)
    const outM = total % 60
    return `${String(outH).padStart(2, '0')}:${String(outM).padStart(2, '0')}`
  }

  const load = async () => {
    setBusy(true)
    try {
      const res = await fetchUnifiedRiskGlobal()
      setDraft(res)
      setError(null)
      setLoaded(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load risk settings')
      setDraft(null)
      setLoaded(false)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    if (!loaded || !draft) return
    const existing = extractUiPauseAutoWindow(String(draft.no_trade_rules || ''))
    if (existing) {
      if (!pauseStart) setPauseStart(existing.start)
      if (!pauseEnd) setPauseEnd(existing.end)
      return
    }
    if (!pauseStart) {
      const s = nowIstHHMM()
      if (s) setPauseStart(s)
    }
    if (!pauseEnd) {
      const s = nowIstHHMM()
      if (s) setPauseEnd(addMinutesHHMM(s, 30))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, draft])

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Risk globals
        </Typography>
        <Tooltip title="Refresh" arrow placement="top">
          <span>
            <IconButton size="small" onClick={() => void load()} disabled={busy || saving}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Button
          size="small"
          variant="contained"
          disabled={!loaded || !draft || saving}
          onClick={async () => {
            if (!draft) return
            setSaving(true)
            try {
              const updated = await updateUnifiedRiskGlobal({
                enabled: Boolean(draft.enabled),
                manual_override_enabled: Boolean(draft.manual_override_enabled),
                baseline_equity_inr: numOrZero(draft.baseline_equity_inr),
                no_trade_rules: String(draft.no_trade_rules || ''),
              })
              setDraft(updated)
              setError(null)
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Failed to save risk settings')
            } finally {
              setSaving(false)
            }
          }}
        >
          {saving ? 'Saving…' : 'Save globals'}
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        System-wide toggles. Manual override applies only to explicit manual orders (not TradingView / deployments).
      </Typography>

      {!loaded || !draft ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
          {busy ? <CircularProgress size={18} /> : null}
          <Typography variant="body2" color="text.secondary">
            {busy ? 'Loading…' : 'Not loaded.'}
          </Typography>
        </Box>
      ) : (
        <Box sx={{ mt: 1.5, display: 'grid', gap: 1.5 }}>
          <FormControlLabel
            control={
              <Switch
                checked={Boolean(draft.enabled)}
                onChange={(e) => setDraft((p) => (p ? { ...p, enabled: e.target.checked } : p))}
              />
            }
            label="Enable risk enforcement (global)"
          />

          <FormControlLabel
            control={
              <Switch
                checked={Boolean(draft.manual_override_enabled)}
                onChange={(e) =>
                  setDraft((p) =>
                    p
                      ? {
                          ...p,
                          manual_override_enabled: e.target.checked
                            ? typeof window !== 'undefined' && typeof window.confirm === 'function'
                              ? window.confirm(
                                  'Enable MANUAL override?\n\nThis is a high-risk escape hatch.\n\nWhen ON:\n- MANUAL orders can bypass ALL risk blocks (including drawdown HARD_STOP and execution safety guards).\n- TradingView / deployments remain fully enforced.\n- Structural validity checks still apply.\n\nEnable only for rare, deliberate exceptions and turn it OFF immediately after.',
                                )
                              : false
                              : false,
                        }
                      : p,
                  )
                }
              />
            }
            label="Manual override (manual orders only; bypass risk blocks)"
          />

          {draft.manual_override_enabled ? (
            <Alert severity="error">
              Manual override is ON. For explicit MANUAL orders, SigmaTrader will warn but will not block on risk thresholds (including drawdown HARD_STOP and execution safety guards). TradingView / deployments remain enforced.
              Use this only for rare, deliberate exceptions and turn it OFF immediately after.
            </Alert>
          ) : null}

          <TextField
            size="small"
            type="number"
            label="Baseline equity (INR)"
            value={draft.baseline_equity_inr ?? 0}
            onChange={(e) =>
              setDraft((p) => (p ? { ...p, baseline_equity_inr: numOrZero(e.target.value) } : p))
            }
            helperText="Used for % caps and drawdown calculations."
            sx={{ maxWidth: 320 }}
          />

          {(() => {
            const pauseWindow = extractUiPauseAutoWindow(String(draft.no_trade_rules || ''))
            const pauseEnabled = Boolean(pauseWindow)

            const applyPauseRuleIfEnabled = (start: string, end: string) => {
              if (!pauseEnabled) return
              if (!isValidHHMM(start) || !isValidHHMM(end)) return
              setDraft((p) =>
                p ? { ...p, no_trade_rules: setUiPauseAutoRule(p.no_trade_rules ?? '', start, end) } : p,
              )
            }

            return (
              <Box sx={{ display: 'grid', gap: 0.75 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={pauseEnabled}
                      onChange={(e) => {
                        const next = e.target.checked
                        if (!next) {
                          setPauseInputError(null)
                          setDraft((p) =>
                            p ? { ...p, no_trade_rules: clearUiPauseAutoRule(p.no_trade_rules ?? '') } : p,
                          )
                          return
                        }

                        const start = String(pauseStart || '').trim()
                        const end = String(pauseEnd || '').trim()
                        if (!isValidHHMM(start) || !isValidHHMM(end)) {
                          setPauseInputError('Invalid time range. Use HH:MM start and end (IST).')
                          return
                        }
                        setPauseInputError(null)
                        setDraft((p) =>
                          p
                            ? { ...p, no_trade_rules: setUiPauseAutoRule(p.no_trade_rules ?? '', start, end) }
                            : p,
                        )
                      }}
                    />
                  }
                  label={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                      <span>Pause AUTO execution (route AUTO orders to manual queue)</span>
                      <Tooltip
                        arrow
                        placement="top"
                        title={
                          <Box sx={{ whiteSpace: 'pre-line' }}>
                            {'PAUSE_AUTO: during the window, AUTO executions are not sent to broker; orders are moved to the Waiting Queue as MANUAL.\n\nNO_TRADE: legacy alias for PAUSE_AUTO (no auto-resume).\n\nKeys let you target BUY/SELL/CNC/MIS.'}
                          </Box>
                        }
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <HelpOutlineIcon fontSize="small" />
                        </span>
                      </Tooltip>
                    </Box>
                  }
                />

                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                  <TextField
                    size="small"
                    type="time"
                    label="Start (IST)"
                    value={pauseStart}
                    onChange={(e) => {
                      const v = String(e.target.value || '')
                      setPauseStart(v)
                      setPauseInputError(null)
                      applyPauseRuleIfEnabled(v, pauseEnd)
                    }}
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ step: 60 }}
                    error={Boolean(pauseInputError)}
                    sx={{ width: 160 }}
                  />
                  <TextField
                    size="small"
                    type="time"
                    label="End (IST)"
                    value={pauseEnd}
                    onChange={(e) => {
                      const v = String(e.target.value || '')
                      setPauseEnd(v)
                      setPauseInputError(null)
                      applyPauseRuleIfEnabled(pauseStart, v)
                    }}
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ step: 60 }}
                    error={Boolean(pauseInputError)}
                    sx={{ width: 160 }}
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                    Writes a tagged rule (`# UI_PAUSE_AUTO`) into “AUTO pause windows” below.
                  </Typography>
                </Box>

                {pauseEnabled && pauseWindow ? (
                  <Alert severity="warning">
                    AUTO execution is paused from {pauseWindow.start} to {pauseWindow.end} (IST). AUTO orders in this
                    window are routed to the Waiting Queue as MANUAL. Click “Save globals” to apply.
                  </Alert>
                ) : null}

                {pauseInputError ? (
                  <Typography variant="caption" color="error">
                    {pauseInputError}
                  </Typography>
                ) : null}
              </Box>
            )
          })()}

          <TextField
            size="small"
            label="AUTO pause windows (IST)"
            value={draft.no_trade_rules ?? ''}
            onChange={(e) =>
              setDraft((p) => (p ? { ...p, no_trade_rules: String(e.target.value) } : p))
            }
            multiline
            minRows={4}
            placeholder={`09:15-09:30 PAUSE_AUTO ALL\n09:15-09:30 PAUSE_AUTO BUY`}
            helperText="Advanced. One rule per line: 'HH:MM-HH:MM PAUSE_AUTO|TRADE|NO_TRADE keys'. keys: ALL, BUY, SELL, CNC, MIS, CNC_BUY, CNC_SELL, MIS_BUY, MIS_SELL. PAUSE_AUTO routes AUTO orders to the Waiting Queue (MANUAL). NO_TRADE is a legacy alias for PAUSE_AUTO (no auto-resume)."
            sx={{ maxWidth: 740 }}
          />
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mt: 1.5 }}>
          {error}
        </Alert>
      )}
    </Paper>
  )
}
