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

          <TextField
            size="small"
            label="No-trade windows (IST)"
            value={draft.no_trade_rules ?? ''}
            onChange={(e) =>
              setDraft((p) => (p ? { ...p, no_trade_rules: String(e.target.value) } : p))
            }
            multiline
            minRows={4}
            placeholder={`09:15-09:20 NO_TRADE ALL\n09:20-09:25 NO_TRADE CNC_BUY,MIS_BUY`}
            helperText="Advanced. One rule per line: 'HH:MM-HH:MM TRADE|NO_TRADE keys'. keys: ALL, BUY, SELL, CNC, MIS, CNC_BUY, CNC_SELL, MIS_BUY, MIS_SELL. AUTO dispatch is deferred to Waiting Queue during NO_TRADE."
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
