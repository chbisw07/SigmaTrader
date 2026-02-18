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
  fetchAiSettingsAudit,
  testKiteMcpConnection,
  updateAiSettings,
  type AiSettings,
} from '../services/aiSettings'
import { setAiTmFeatureFlag } from '../config/aiFeatures'
import { AiProviderSettingsPanel } from './ai/AiProviderSettingsPanel'

function statusChip(status: string) {
  const s = (status || '').toLowerCase()
  const label =
    s === 'connected'
      ? 'Connected'
      : s === 'disconnected'
        ? 'Disconnected'
        : s === 'error'
          ? 'Error'
          : 'Unknown'
  const color: 'default' | 'success' | 'warning' | 'error' =
    s === 'connected' ? 'success' : s === 'error' ? 'error' : s === 'disconnected' ? 'warning' : 'default'
  return <Chip size="small" label={label} color={color} />
}

export function AiSettingsPanel() {
  const [settings, setSettings] = useState<AiSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [confirmExecOpen, setConfirmExecOpen] = useState(false)
  const [confirmExecChecked, setConfirmExecChecked] = useState(false)

  const [auditOpen, setAuditOpen] = useState(false)
  const [auditRows, setAuditRows] = useState<any[]>([])
  const [auditError, setAuditError] = useState<string | null>(null)

  const connectedForExecution = useMemo(() => {
    if (!settings) return false
    const kite = settings.kite_mcp
    return Boolean(settings.feature_flags.kite_mcp_enabled && kite.server_url && kite.last_status === 'connected')
  }, [settings])

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
      setError('Cannot enable execution: Kite MCP must be connected (Test Connection) and enabled.')
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

  const handleTestKite = async (withCapabilities: boolean) => {
    if (!settings) return
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      await testKiteMcpConnection({
        server_url: settings.kite_mcp.server_url ?? undefined,
        fetch_capabilities: withCapabilities,
      })
      await load()
      setSuccess('Kite MCP test completed.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to test Kite MCP')
    } finally {
      setBusy(false)
    }
  }

  const openAudit = async () => {
    setAuditOpen(true)
    setAuditRows([])
    setAuditError(null)
    try {
      const data = await fetchAiSettingsAudit({ limit: 100, offset: 0 })
      setAuditRows(data.items ?? [])
    } catch (e) {
      setAuditError(e instanceof Error ? e.message : 'Failed to load audit log')
    }
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

  const kite = settings.kite_mcp
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

          <FormControlLabel
            control={
              <Switch
                checked={settings.feature_flags.kite_mcp_enabled}
                onChange={(_, v) =>
                  void patch({ feature_flags: { ...settings.feature_flags, kite_mcp_enabled: v } } as any)
                }
              />
            }
            label="Kite MCP enabled (broker-truth access)"
          />

          <FormControlLabel
            control={
              <Switch
                checked={settings.feature_flags.monitoring_enabled}
                onChange={(_, v) =>
                  void patch({ feature_flags: { ...settings.feature_flags, monitoring_enabled: v } } as any)
                }
              />
            }
            label="Monitoring enabled"
          />

          <Divider />

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

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
          <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 200 }}>
            Kite MCP
          </Typography>
          {statusChip(kite.last_status)}
          <Button size="small" variant="outlined" onClick={() => void openAudit()}>
            View Audit Log
          </Button>
        </Stack>

        <Typography variant="body2" color="text.secondary" sx={{ pt: 0.75 }}>
          Kite MCP provides broker-truth snapshots and (when enabled) broker execution. SigmaTrader still maintains an
          expected ledger and reconciles.
        </Typography>

        {kite.last_error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {kite.last_error}
          </Alert>
        )}

        <Stack spacing={1.25} sx={{ pt: 1.5 }}>
          <TextField
            label="MCP server URL"
            value={kite.server_url ?? ''}
            onChange={(e) =>
              setSettings((prev) =>
                prev
                  ? { ...prev, kite_mcp: { ...prev.kite_mcp, server_url: e.target.value } }
                  : prev,
              )
            }
            onBlur={() => void patch({ kite_mcp: { server_url: kite.server_url ?? null } } as any)}
            size="small"
            placeholder="https://localhost:1234"
            fullWidth
          />
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <TextField
              label="Transport mode"
              value={kite.transport_mode}
              onChange={(e) =>
                void patch({ kite_mcp: { transport_mode: e.target.value } } as any)
              }
              size="small"
              select
              sx={{ width: 180 }}
            >
              <MenuItem value="local">local</MenuItem>
              <MenuItem value="remote">remote</MenuItem>
            </TextField>
            <TextField
              label="Auth method"
              value={kite.auth_method}
              onChange={(e) => void patch({ kite_mcp: { auth_method: e.target.value } } as any)}
              size="small"
              select
              sx={{ width: 180 }}
            >
              <MenuItem value="none">none</MenuItem>
              <MenuItem value="token">token</MenuItem>
              <MenuItem value="oauth">oauth</MenuItem>
              <MenuItem value="totp">totp</MenuItem>
            </TextField>
            <TextField
              label="Auth profile ref"
              value={kite.auth_profile_ref ?? ''}
              onChange={(e) => void patch({ kite_mcp: { auth_profile_ref: e.target.value || null } } as any)}
              size="small"
              sx={{ minWidth: 240, flex: 1 }}
            />
          </Stack>

          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={kite.scopes.read_only}
                  onChange={(_, v) =>
                    void patch({ kite_mcp: { scopes: { ...kite.scopes, read_only: v } } } as any)
                  }
                />
              }
              label="Read-only"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={kite.scopes.trade}
                  onChange={(_, v) =>
                    void patch({ kite_mcp: { scopes: { ...kite.scopes, trade: v } } } as any)
                  }
                />
              }
              label="Trade"
            />
            <TextField
              label="Adapter"
              value={kite.broker_adapter}
              onChange={(e) => void patch({ kite_mcp: { broker_adapter: e.target.value } } as any)}
              size="small"
              select
              sx={{ width: 180 }}
            >
              <MenuItem value="zerodha">zerodha</MenuItem>
              <MenuItem value="angelone">angelone</MenuItem>
            </TextField>
          </Stack>

          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => void handleTestKite(false)}
              disabled={busy || !kite.server_url}
            >
              Test Connection
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => void handleTestKite(true)}
              disabled={busy || !kite.server_url}
            >
              Fetch Capabilities
            </Button>
          </Stack>

          {kite.capabilities_cache && Object.keys(kite.capabilities_cache).length > 0 && (
            <Box sx={{ pt: 1 }}>
              <Typography variant="subtitle2" color="text.secondary">
                Capabilities (cached)
              </Typography>
              <Paper variant="outlined" sx={{ p: 1, mt: 0.5, bgcolor: 'background.default' }}>
                <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(kite.capabilities_cache, null, 2)}
                </Typography>
              </Paper>
            </Box>
          )}
        </Stack>
      </Paper>

      <AiProviderSettingsPanel />

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
            - Kite MCP enabled + Connected: {connectedForExecution ? 'yes' : 'no'}
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

      <Dialog open={auditOpen} onClose={() => setAuditOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>AI Audit Log</DialogTitle>
        <DialogContent>
          {auditError && (
            <Alert severity="error" sx={{ mb: 1 }}>
              {auditError}
            </Alert>
          )}
          {auditRows.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No audit events yet.
            </Typography>
          ) : (
            <Stack spacing={1}>
              {auditRows.map((r) => (
                <Paper key={r.id} variant="outlined" sx={{ p: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    {r.created_at} • {r.level} • {r.category}
                  </Typography>
                  <Typography variant="body2">{r.message}</Typography>
                  {r.details && (
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', pt: 0.5 }}>
                      {JSON.stringify(r.details, null, 2)}
                    </Typography>
                  )}
                </Paper>
              ))}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAuditOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
