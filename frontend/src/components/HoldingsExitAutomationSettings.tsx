import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import FormControlLabel from '@mui/material/FormControlLabel'
import Paper from '@mui/material/Paper'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import {
  fetchHoldingsExitConfig,
  updateHoldingsExitConfig,
  type HoldingsExitConfigRead,
} from '../services/holdingsExit'

export function HoldingsExitAutomationSettings() {
  const [cfg, setCfg] = useState<HoldingsExitConfigRead | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [enabledDraft, setEnabledDraft] = useState(false)
  const [allowlistDraft, setAllowlistDraft] = useState('')

  const load = async () => {
    setBusy(true)
    try {
      const res = await fetchHoldingsExitConfig()
      setCfg(res)
      setEnabledDraft(Boolean(res.enabled))
      setAllowlistDraft(res.allowlist_symbols ?? '')
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load holdings exit config')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const save = async (next?: { enabled?: boolean; allowlist_symbols?: string | null }) => {
    setBusy(true)
    try {
      const res = await updateHoldingsExitConfig({
        enabled: next?.enabled ?? enabledDraft,
        allowlist_symbols:
          next?.allowlist_symbols ??
          (allowlistDraft.trim() ? allowlistDraft.trim() : null),
      })
      setCfg(res)
      setEnabledDraft(Boolean(res.enabled))
      setAllowlistDraft(res.allowlist_symbols ?? '')
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update holdings exit config')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Holdings exit automation (MVP)
        </Typography>
        <Chip
          size="small"
          label={cfg ? `Source: ${cfg.source}` : 'Source: —'}
          color={cfg?.source === 'db' ? 'success' : 'default'}
        />
        <Button
          size="small"
          variant="outlined"
          startIcon={<RefreshIcon />}
          disabled={busy}
          onClick={() => void load()}
        >
          Refresh
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1.5 }}>
        When enabled, SigmaTrader monitors Zerodha CNC holdings and can create a CNC SELL order in
        the Waiting Queue when targets are met (manual-only).
      </Typography>

      <Box sx={{ display: 'grid', gap: 1.5, maxWidth: 720 }}>
        <FormControlLabel
          control={
            <Switch
              checked={enabledDraft}
              onChange={(e) => {
                const checked = e.target.checked
                setEnabledDraft(checked)
                void save({ enabled: checked })
              }}
              disabled={busy}
            />
          }
          label="Enable holdings exit automation (MVP)"
        />

        <TextField
          label="Allowlist symbols (optional)"
          value={allowlistDraft}
          onChange={(e) => setAllowlistDraft(e.target.value)}
          disabled={busy}
          placeholder="NSE:INFY,BSE:TCS or INFY"
          helperText="If set, only these symbols can create subscriptions. Leave blank to allow all."
        />

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button
            size="small"
            variant="contained"
            disabled={busy}
            onClick={() => void save()}
          >
            {busy ? 'Saving…' : 'Save holdings exit settings'}
          </Button>
          <Button
            size="small"
            variant="outlined"
            disabled={busy}
            onClick={() => {
              setEnabledDraft(Boolean(cfg?.enabled))
              setAllowlistDraft(cfg?.allowlist_symbols ?? '')
            }}
          >
            Reset
          </Button>
        </Box>

        {error && <Alert severity="error">{error}</Alert>}
      </Box>
    </Paper>
  )
}
