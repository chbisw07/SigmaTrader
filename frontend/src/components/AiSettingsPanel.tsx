import { useEffect, useMemo, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import MenuItem from '@mui/material/MenuItem'

import {
  fetchAiSettings,
  updateAiSettings,
  type AiSettings,
} from '../services/aiSettings'
import { setAiTmFeatureFlag } from '../config/aiFeatures'
import { AiProviderSettingsPanel } from './ai/AiProviderSettingsPanel'

export function AiSettingsPanel() {
  const [settings, setSettings] = useState<AiSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [confirmExecOpen, setConfirmExecOpen] = useState(false)
  const [confirmExecChecked, setConfirmExecChecked] = useState(false)

  const connectedForExecution = useMemo(() => {
    if (!settings) return false
    const kite = settings.kite_mcp
    return Boolean(settings.feature_flags.kite_mcp_enabled && kite.server_url && kite.last_status === 'connected')
  }, [settings])

  const hybrid = settings?.hybrid_llm
  const guardrails = settings?.tool_guardrails ?? { tavily_max_calls_per_session: 10, tavily_warning_threshold: 8 }

  const load = async () => {
    setError(null)
    try {
      const s = await fetchAiSettings()
      setSettings(s)
      // Keep local flags in sync so the UI (assistant panel) feels immediate.
      setAiTmFeatureFlag('ai_assistant_enabled', Boolean(s.feature_flags.ai_assistant_enabled))
      setAiTmFeatureFlag('ai_execution_enabled', Boolean(s.feature_flags.ai_execution_enabled))
      setAiTmFeatureFlag('kite_mcp_enabled', Boolean(s.feature_flags.kite_mcp_enabled))
      setAiTmFeatureFlag('monitoring_enabled', Boolean(s.feature_flags.monitoring_enabled))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load AI settings')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const patch = async (partial: Partial<AiSettings>) => {
    if (!settings) return
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const next = await updateAiSettings(partial as any)
      setSettings(next)
      setAiTmFeatureFlag('ai_assistant_enabled', Boolean(next.feature_flags.ai_assistant_enabled))
      setAiTmFeatureFlag('ai_execution_enabled', Boolean(next.feature_flags.ai_execution_enabled))
      setAiTmFeatureFlag('kite_mcp_enabled', Boolean(next.feature_flags.kite_mcp_enabled))
      setAiTmFeatureFlag('monitoring_enabled', Boolean(next.feature_flags.monitoring_enabled))
      setSuccess('Saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save AI settings')
    } finally {
      setBusy(false)
    }
  }

  const handleToggleExecution = (enabled: boolean) => {
    if (!settings) return
    if (!enabled) {
      void patch({ feature_flags: { ...settings.feature_flags, ai_execution_enabled: false } } as any)
      return
    }
    setConfirmExecChecked(false)
    setConfirmExecOpen(true)
  }

  const handleConfirmExecutionEnable = async () => {
    if (!settings) return
    if (!confirmExecChecked) return
    if (!connectedForExecution) {
      setError('Cannot enable execution: Kite MCP must be enabled and connected (run Test Connection in Settings → MCP & Tools).')
      setConfirmExecOpen(false)
      return
    }
    setConfirmExecOpen(false)
    await patch({ feature_flags: { ...settings.feature_flags, ai_execution_enabled: true } } as any)
  }

  const handleKillSwitch = async () => {
    if (!settings) return
    await patch({
      kill_switch: { ...settings.kill_switch, ai_execution_kill_switch: true },
      feature_flags: { ...settings.feature_flags, ai_execution_enabled: false },
    } as any)
  }


  if (!settings) {
    return (
      <Box>
        <Typography variant="h6">AI Settings</Typography>
        {error ? (
          <Alert severity="error" sx={{ mt: 1 }}>
            {error}
          </Alert>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Loading…
          </Typography>
        )}
      </Box>
    )
  }

  const execKill = Boolean(settings.kill_switch.ai_execution_kill_switch)

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6">AI Settings</Typography>
        <Button size="small" variant="outlined" onClick={() => void load()} disabled={busy}>
          Refresh
        </Button>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
      {success && <Alert severity="success">{success}</Alert>}

      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle1">Feature Flags / Modes</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ pt: 0.5 }}>
          These flags are persisted server-side and also mirrored locally to control UI visibility.
        </Typography>

        <Stack spacing={1.25} sx={{ pt: 1.5 }}>
          <FormControlLabel
            control={
              <Switch
                checked={settings.feature_flags.ai_assistant_enabled}
                onChange={(_, v) =>
                  void patch({ feature_flags: { ...settings.feature_flags, ai_assistant_enabled: v } } as any)
                }
              />
            }
            label="AI assistant enabled"
          />

          <Divider />

          <Alert severity="info">
            MCP servers (Kite MCP and future tool servers) are configured in <b>Settings → MCP &amp; Tools</b>.
          </Alert>

          <Alert severity="warning">
            Execution is policy-gated and audit-logged. Orchestrator is not fully integrated yet; enable with care.
          </Alert>

          <FormControlLabel
            control={
              <Switch
                checked={settings.feature_flags.ai_execution_enabled}
                onChange={(_, v) => handleToggleExecution(v)}
                disabled={execKill}
              />
            }
            label="AI execution enabled"
          />

          <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
            <Chip
              size="small"
              label={execKill ? 'Kill switch: ON' : 'Kill switch: OFF'}
              color={execKill ? 'error' : 'default'}
            />
            <Button size="small" color="error" variant="outlined" onClick={() => void handleKillSwitch()} disabled={busy}>
              Disable all AI execution now
            </Button>
          </Stack>
        </Stack>
      </Paper>

      <AiProviderSettingsPanel title="Remote Model / Provider" />

      <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">Hybrid LLM Gateway</Typography>
          <Typography variant="body2" color="text.secondary">
            Routes all tool execution through the Local Security Gateway (LSG). Remote models do not receive tool handles
            and can only request allowlisted capabilities.
          </Typography>

          <FormControlLabel
            control={
              <Switch
                checked={Boolean(hybrid?.enabled)}
                onChange={(_, v) => void patch({ hybrid_llm: { enabled: v } } as any)}
                disabled={busy || !settings}
              />
            }
            label="Enable Hybrid LLM Gateway"
          />

          {hybrid?.enabled && (
            <>
              <TextField
                select
                size="small"
                label="Mode"
                value={hybrid.mode || 'AUTO'}
                onChange={(e) => void patch({ hybrid_llm: { mode: e.target.value as any } } as any)}
                disabled={busy}
              >
                <MenuItem value="AUTO">Auto (AUTO)</MenuItem>
                <MenuItem value="LOCAL_ONLY">Local (LOCAL_ONLY)</MenuItem>
                <MenuItem value="REMOTE_ONLY">Remote (REMOTE_ONLY)</MenuItem>
                <MenuItem value="HYBRID">Hybrid (HYBRID)</MenuItem>
              </TextField>

              <TextField
                select
                size="small"
                label="Remote portfolio detail level"
                value={(hybrid as any).remote_portfolio_detail_level || 'DIGEST_ONLY'}
                onChange={(e) =>
                  void patch({ hybrid_llm: { remote_portfolio_detail_level: e.target.value as any } } as any)
                }
                disabled={busy}
                helperText="Controls what Tier-2 portfolio telemetry (holdings/positions/orders/margins) can be sent to a remote model. Tier-3 PII/secrets are always blocked."
              >
                <MenuItem value="OFF">Off (OFF)</MenuItem>
                <MenuItem value="DIGEST_ONLY">Digests only (DIGEST_ONLY)</MenuItem>
                <MenuItem value="FULL_SANITIZED">Full sanitized (FULL_SANITIZED)</MenuItem>
              </TextField>

              <FormControlLabel
                control={
                  <Switch
                    checked={Boolean(hybrid.allow_remote_market_data_tools)}
                    onChange={(_, v) => void patch({ hybrid_llm: { allow_remote_market_data_tools: v } } as any)}
                    disabled={busy}
                  />
                }
                label="Remote may request market-data tools"
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={Boolean(hybrid.allow_remote_account_digests)}
                    onChange={(_, v) => void patch({ hybrid_llm: { allow_remote_account_digests: v } } as any)}
                    disabled={busy}
                  />
                }
                label="Remote may request account digests"
              />

              <Alert severity="info">
                Remote requests are validated and audited. Trading write tools and identity/auth are always denied to
                remote models; execution remains gated by explicit user authorization and kill switches.
              </Alert>

              <Alert severity="info">
                In HYBRID mode, the remote reasoner uses the <b>Remote Model / Provider</b> configured above. To use a
                different local model for LOCAL_ONLY (or for future hybrid formatting), configure <b>Hybrid Local Model / Provider</b>{' '}
                below.
              </Alert>
            </>
          )}
        </Stack>
      </Paper>

      {hybrid?.enabled && (
        <Box sx={{ mt: 2 }}>
          <AiProviderSettingsPanel slot="hybrid_local" title="Hybrid Local Model / Provider" />
        </Box>
      )}

      <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">External Tool Guardrails</Typography>
          <Typography variant="body2" color="text.secondary">
            Session-scoped limits to prevent runaway tool loops and unexpected credit usage.
          </Typography>
          <TextField
            size="small"
            type="number"
            label="Tavily max calls per session"
            value={Number(guardrails.tavily_max_calls_per_session ?? 10)}
            onChange={(e) =>
              void patch({ tool_guardrails: { tavily_max_calls_per_session: Number(e.target.value || 0) } } as any)
            }
            disabled={busy}
            inputProps={{ min: 0, max: 10000, step: 1 }}
          />
          <TextField
            size="small"
            type="number"
            label="Tavily warning threshold"
            value={Number(guardrails.tavily_warning_threshold ?? 8)}
            onChange={(e) =>
              void patch({ tool_guardrails: { tavily_warning_threshold: Number(e.target.value || 0) } } as any)
            }
            disabled={busy}
            helperText="Calls at/after this threshold show a soft warning; calls beyond the max require explicit approval."
            inputProps={{ min: 0, max: 10000, step: 1 }}
          />
        </Stack>
      </Paper>

      <Dialog open={confirmExecOpen} onClose={() => setConfirmExecOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Enable AI execution?</DialogTitle>
        <DialogContent>
          <Alert severity="warning">
            Enabling execution allows SigmaTrader to place broker orders (policy-gated) when user instructions authorize it.
          </Alert>
          <Typography variant="body2" color="text.secondary" sx={{ pt: 1 }}>
            Requirements:
          </Typography>
          <Typography variant="body2" color={connectedForExecution ? 'text.primary' : 'error'} sx={{ pt: 0.5 }}>
            - Kite MCP enabled + Connected (Settings → MCP & Tools): {connectedForExecution ? 'yes' : 'no'}
          </Typography>
          <FormControlLabel
            control={<Checkbox checked={confirmExecChecked} onChange={(_, v) => setConfirmExecChecked(v)} />}
            label="I understand the risks and want to enable execution."
            sx={{ pt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmExecOpen(false)}>Cancel</Button>
          <Button variant="contained" color="warning" disabled={!confirmExecChecked} onClick={() => void handleConfirmExecutionEnable()}>
            Enable
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
