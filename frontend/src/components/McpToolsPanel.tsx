import { useEffect, useMemo, useState } from 'react'
import Alert from '@mui/material/Alert'
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

import { setAiTmFeatureFlag } from '../config/aiFeatures'
import { fetchAiSettingsAudit } from '../services/aiSettings'
import {
  fetchGenericMcpServerConfig,
  fetchKiteMcpLiveStatus,
  fetchKiteMcpServerConfig,
  fetchKiteMcpSnapshot,
  listMcpServers,
  startKiteMcpAuth,
  testKiteMcpConnection,
  testMcpServer,
  updateGenericMcpServerConfig,
  updateKiteMcpServerConfig,
  type GenericMcpServerConfig,
  type KiteMcpLiveStatus,
  type KiteMcpServerConfig,
  type KiteMcpStatus,
  type McpServerCard,
  type McpServersSummaryResponse,
} from '../services/mcpServers'
import { McpConsolePanel } from './mcp/McpConsolePanel'
import { McpJsonConfigEditor } from './mcp/McpJsonConfigEditor'

function statusChip(status: KiteMcpStatus | string) {
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

function normalizeEnvText(text: string): { ok: true; value: Record<string, string> } | { ok: false; error: string } {
  try {
    const v = JSON.parse(text || '{}')
    if (v === null || typeof v !== 'object' || Array.isArray(v)) return { ok: false, error: 'env must be a JSON object.' }
    const out: Record<string, string> = {}
    for (const [k, val] of Object.entries(v)) out[String(k)] = String(val)
    return { ok: true, value: out }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Invalid JSON' }
  }
}

export function McpToolsPanel() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [summary, setSummary] = useState<McpServersSummaryResponse | null>(null)
  const [kiteCfg, setKiteCfg] = useState<KiteMcpServerConfig | null>(null)
  const [kiteLive, setKiteLive] = useState<KiteMcpLiveStatus | null>(null)
  const [tavilyCfg, setTavilyCfg] = useState<GenericMcpServerConfig | null>(null)

  const [authOpen, setAuthOpen] = useState(false)
  const [authWarning, setAuthWarning] = useState<string>('')
  const [authUrl, setAuthUrl] = useState<string>('')

  const [auditOpen, setAuditOpen] = useState(false)
  const [auditRows, setAuditRows] = useState<any[]>([])
  const [auditError, setAuditError] = useState<string | null>(null)

  const [snapshotSummary, setSnapshotSummary] = useState<string | null>(null)

  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [tavilyArgsDraft, setTavilyArgsDraft] = useState<string>('')
  const [tavilyEnvDraft, setTavilyEnvDraft] = useState<string>('{}')
  const [tavilyEnvError, setTavilyEnvError] = useState<string | null>(null)

  const serverOptions = useMemo(() => {
    const rows = (summary?.servers ?? []) as McpServerCard[]
    return rows.map((s) => ({ id: s.id, label: s.label, enabled: s.enabled, configured: s.configured }))
  }, [summary])

  const load = async () => {
    setError(null)
    try {
      const [sum, kite, tavily] = await Promise.all([
        listMcpServers(),
        fetchKiteMcpServerConfig(),
        fetchGenericMcpServerConfig('tavily'),
      ])
      setSummary(sum)
      setKiteCfg(kite)
      setTavilyCfg(tavily)
      setAiTmFeatureFlag('kite_mcp_enabled', Boolean(kite.enabled))
      setAiTmFeatureFlag('monitoring_enabled', Boolean(kite.monitoring_enabled))
      try {
        const st = await fetchKiteMcpLiveStatus()
        setKiteLive(st)
      } catch {
        setKiteLive(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load MCP settings')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    if (!tavilyCfg) return
    setTavilyArgsDraft(Array.isArray(tavilyCfg.args) ? tavilyCfg.args.join(' ') : '')
    setTavilyEnvDraft(JSON.stringify(tavilyCfg.env ?? {}, null, 2))
    setTavilyEnvError(null)
  }, [tavilyCfg])

  useEffect(() => {
    const handler = (ev: MessageEvent) => {
      if (ev?.data?.type === 'kite_mcp_auth_complete') {
        void refreshKiteLiveStatus()
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  const refreshKiteLiveStatus = async () => {
    try {
      const st = await fetchKiteMcpLiveStatus()
      setKiteLive(st)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch Kite MCP status')
    }
  }

  const patchKite = async (partial: any) => {
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const next = await updateKiteMcpServerConfig(partial)
      setKiteCfg(next)
      setAiTmFeatureFlag('kite_mcp_enabled', Boolean(next.enabled))
      setAiTmFeatureFlag('monitoring_enabled', Boolean(next.monitoring_enabled))
      setSuccess('Saved.')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save Kite MCP config')
    } finally {
      setBusy(false)
    }
  }

  const patchTavily = async (next: GenericMcpServerConfig) => {
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const saved = await updateGenericMcpServerConfig('tavily', next)
      setTavilyCfg(saved)
      setSuccess('Saved.')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save Tavily MCP config')
    } finally {
      setBusy(false)
    }
  }

  const startAuth = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await startKiteMcpAuth()
      setAuthWarning(res.warning_text)
      setAuthUrl(res.login_url)
      setAuthOpen(true)
      try {
        window.open(res.login_url, '_blank', 'noopener,noreferrer')
      } catch {
        // ignore
      }
      await refreshKiteLiveStatus()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start Kite MCP auth')
    } finally {
      setBusy(false)
    }
  }

  const handleTestKite = async (withCapabilities: boolean) => {
    if (!kiteCfg) return
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      await testKiteMcpConnection({ server_url: kiteCfg.server_url ?? null, fetch_capabilities: withCapabilities })
      await load()
      setSuccess('Kite MCP test completed.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to test Kite MCP')
    } finally {
      setBusy(false)
    }
  }

  const handleTestTavily = async () => {
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      await testMcpServer('tavily')
      await load()
      setSuccess('Tavily MCP test completed.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to test Tavily MCP')
    } finally {
      setBusy(false)
    }
  }

  const fetchSnapshot = async () => {
    setBusy(true)
    setError(null)
    setSnapshotSummary(null)
    try {
      const snap = await fetchKiteMcpSnapshot('default')
      const holdings = Array.isArray(snap?.holdings) ? snap.holdings.length : 0
      const positions = Array.isArray(snap?.positions) ? snap.positions.length : 0
      const orders = Array.isArray(snap?.orders) ? snap.orders.length : 0
      setSnapshotSummary(`Snapshot fetched: holdings=${holdings}, positions=${positions}, orders=${orders}`)
      await refreshKiteLiveStatus()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Snapshot fetch failed')
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

  const kiteEnabled = Boolean(kiteCfg?.enabled)
  const monitoringEnabled = Boolean(kiteCfg?.monitoring_enabled)

  const tavilyEnabled = Boolean(tavilyCfg?.enabled)
  const tavilyTransport = (tavilyCfg?.transport || 'sse') as 'sse' | 'stdio'
  const tavilyUrl = tavilyCfg?.url ?? ''
  const tavilyCmd = tavilyCfg?.command ?? ''
  const tavilyArgs = tavilyArgsDraft
  const tavilyEnvText = tavilyEnvDraft

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6">MCP & Tools</Typography>
        <Button size="small" variant="outlined" onClick={() => void load()} disabled={busy}>
          Refresh
        </Button>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
      {success && <Alert severity="success">{success}</Alert>}

      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle1">Summary</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ pt: 0.5 }}>
          MCP is the integration layer for external tool servers (broker MCP today; search/tools MCP later).
        </Typography>

        <Stack direction="row" spacing={1} sx={{ pt: 1, flexWrap: 'wrap' }} alignItems="center">
          {(summary?.servers ?? []).map((s) => (
            <Chip key={s.id} size="small" label={`${s.label}: ${String(s.status).toUpperCase()}`} />
          ))}
        </Stack>

        <Stack direction="row" spacing={2} sx={{ pt: 1.5, flexWrap: 'wrap' }} alignItems="center">
          <FormControlLabel
            control={
              <Switch
                checked={monitoringEnabled}
                onChange={(_, v) => void patchKite({ monitoring_enabled: v })}
                disabled={busy}
              />
            }
            label="Monitoring enabled"
          />
          <Button size="small" variant="outlined" onClick={() => setAdvancedOpen((v) => !v)} disabled={busy}>
            {advancedOpen ? 'Hide advanced JSON' : 'Advanced JSON'}
          </Button>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
          <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 200 }}>
            Kite MCP (broker)
          </Typography>
          {statusChip(kiteCfg?.last_status || 'unknown')}
          {kiteLive && (
            <Chip
              size="small"
              label={kiteLive.authorized ? 'Authorized' : 'Not authorized'}
              color={kiteLive.authorized ? 'success' : 'default'}
            />
          )}
          <Button size="small" variant="outlined" onClick={() => void openAudit()}>
            View Audit Log
          </Button>
        </Stack>

        <Typography variant="body2" color="text.secondary" sx={{ pt: 0.75 }}>
          Broker-truth snapshots and (when explicitly enabled) broker execution. Execution remains policy-gated and
          audit-logged.
        </Typography>

        {kiteCfg?.last_error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {kiteCfg.last_error}
          </Alert>
        )}

        {kiteLive?.last_error && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {kiteLive.last_error}
          </Alert>
        )}

        <Stack spacing={1.25} sx={{ pt: 1.5 }}>
          <FormControlLabel
            control={
              <Switch checked={kiteEnabled} onChange={(_, v) => void patchKite({ enabled: v })} disabled={busy} />
            }
            label="Enable Kite MCP (broker-truth access)"
          />

          <TextField
            label="MCP server URL"
            value={kiteCfg?.server_url ?? ''}
            onChange={(e) => setKiteCfg((prev) => (prev ? { ...prev, server_url: e.target.value } : prev))}
            onBlur={() => void patchKite({ server_url: (kiteCfg?.server_url ?? '').trim() || null })}
            fullWidth
            size="small"
            disabled={busy}
            placeholder="https://mcp.kite.trade/sse"
          />

          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <TextField
              select
              size="small"
              label="Transport mode"
              value={kiteCfg?.transport_mode || 'remote'}
              onChange={(e) => void patchKite({ transport_mode: e.target.value })}
              sx={{ minWidth: 180 }}
              disabled={busy}
            >
              <MenuItem value="remote">remote</MenuItem>
              <MenuItem value="local">local (future)</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label="Auth method"
              value={kiteCfg?.auth_method || 'none'}
              onChange={(e) => void patchKite({ auth_method: e.target.value })}
              sx={{ minWidth: 180 }}
              disabled={busy}
            >
              <MenuItem value="none">none</MenuItem>
              <MenuItem value="oauth">oauth</MenuItem>
              <MenuItem value="token">token (future)</MenuItem>
              <MenuItem value="totp">totp (future)</MenuItem>
            </TextField>
            <TextField
              size="small"
              label="Auth profile ref"
              value={kiteCfg?.auth_profile_ref ?? ''}
              onChange={(e) => setKiteCfg((prev) => (prev ? { ...prev, auth_profile_ref: e.target.value } : prev))}
              onBlur={() => void patchKite({ auth_profile_ref: (kiteCfg?.auth_profile_ref || '').trim() || null })}
              sx={{ minWidth: 220, flex: 1 }}
              disabled={busy}
              placeholder="default"
            />
          </Stack>

          <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
            <FormControlLabel
              control={
                <Switch
                  checked={Boolean(kiteCfg?.scopes?.read_only)}
                  onChange={(_, v) => void patchKite({ scopes: { ...kiteCfg?.scopes, read_only: v } })}
                  disabled={busy}
                />
              }
              label="Read-only"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={Boolean(kiteCfg?.scopes?.trade)}
                  onChange={(_, v) => void patchKite({ scopes: { ...kiteCfg?.scopes, trade: v } })}
                  disabled={busy}
                />
              }
              label="Trade"
            />
            <TextField
              select
              size="small"
              label="Adapter"
              value={kiteCfg?.broker_adapter || 'zerodha'}
              onChange={(e) => void patchKite({ broker_adapter: e.target.value })}
              sx={{ minWidth: 180 }}
              disabled={busy}
            >
              <MenuItem value="zerodha">zerodha</MenuItem>
              <MenuItem value="angelone">angelone</MenuItem>
            </TextField>
          </Stack>

          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Button size="small" variant="outlined" onClick={() => void handleTestKite(false)} disabled={busy || !kiteCfg?.server_url}>
              Test Connection
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => void handleTestKite(true)}
              disabled={busy || !kiteCfg?.server_url || !kiteLive?.connected}
            >
              Fetch Capabilities
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={() => void startAuth()}
              disabled={busy || !kiteCfg?.server_url || !kiteEnabled}
            >
              Authorize
            </Button>
            <Button size="small" variant="outlined" onClick={() => void refreshKiteLiveStatus()} disabled={busy}>
              Refresh status
            </Button>
            <Button size="small" variant="outlined" onClick={() => void fetchSnapshot()} disabled={busy || !kiteLive?.authorized}>
              Fetch snapshot
            </Button>
          </Stack>

          {snapshotSummary && <Alert severity="success">{snapshotSummary}</Alert>}

          {kiteCfg?.capabilities_cache && Object.keys(kiteCfg.capabilities_cache).length > 0 && (
            <Box sx={{ pt: 1 }}>
              <Typography variant="subtitle2" color="text.secondary">
                Capabilities (cached)
              </Typography>
              <Paper variant="outlined" sx={{ p: 1, mt: 0.5, bgcolor: 'background.default' }}>
                <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(kiteCfg.capabilities_cache, null, 2)}
                </Typography>
              </Paper>
            </Box>
          )}
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
          <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 200 }}>
            Tavily MCP (placeholder)
          </Typography>
          {statusChip((tavilyCfg?.last_status as any) || 'unknown')}
        </Stack>

        <Typography variant="body2" color="text.secondary" sx={{ pt: 0.75 }}>
          Placeholder for future search/tool servers. Configure it now to prepare your deployment; runtime execution will be expanded in follow-up work.
        </Typography>

        {tavilyCfg?.last_error && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {tavilyCfg.last_error}
          </Alert>
        )}

        <Stack spacing={1.25} sx={{ pt: 1.5 }}>
          <FormControlLabel
            control={
              <Switch
                checked={tavilyEnabled}
                onChange={(_, v) => void patchTavily({ ...(tavilyCfg || { enabled: false, transport: 'sse' }), enabled: v })}
                disabled={busy}
              />
            }
            label="Enable Tavily server"
          />

          <TextField
            size="small"
            label="Label"
            value={tavilyCfg?.label ?? ''}
            onChange={(e) => setTavilyCfg((prev) => (prev ? { ...prev, label: e.target.value } : prev))}
            onBlur={() => void patchTavily({ ...(tavilyCfg || { enabled: false, transport: 'sse' }), label: tavilyCfg?.label || null })}
            fullWidth
            disabled={busy}
          />

          <TextField
            select
            size="small"
            label="Transport"
            value={tavilyTransport}
            onChange={(e) => {
              const transport = e.target.value as any
              const next = { ...(tavilyCfg || { enabled: false, transport: 'sse' }), transport }
              setTavilyCfg(next)
              void patchTavily(next)
            }}
            sx={{ maxWidth: 240 }}
            disabled={busy}
          >
            <MenuItem value="sse">Remote SSE (URL)</MenuItem>
            <MenuItem value="stdio">Stdio (command) (future)</MenuItem>
          </TextField>

          {tavilyTransport === 'sse' ? (
            <TextField
              size="small"
              label="Server URL"
              value={tavilyUrl}
              onChange={(e) => setTavilyCfg((prev) => (prev ? { ...prev, url: e.target.value } : prev))}
              onBlur={() =>
                void patchTavily({ ...(tavilyCfg || { enabled: false, transport: 'sse' }), url: (tavilyCfg?.url ?? '').trim() || null })
              }
              fullWidth
              disabled={busy}
              placeholder="https://…/sse"
            />
          ) : (
            <>
              <Alert severity="info">
                Stdio servers are stored for future support. SigmaTrader does not spawn local MCP processes yet.
              </Alert>
              <TextField
                size="small"
                label="Command"
                value={tavilyCmd}
                onChange={(e) => setTavilyCfg((prev) => (prev ? { ...prev, command: e.target.value } : prev))}
                onBlur={() => void patchTavily({ ...(tavilyCfg || { enabled: false, transport: 'stdio' }), command: (tavilyCfg?.command ?? '').trim() || null })}
                fullWidth
                disabled={busy}
                placeholder="npx"
              />
              <TextField
                size="small"
                label="Args (space-separated)"
                value={tavilyArgs}
                onChange={(e) => setTavilyArgsDraft(e.target.value)}
                onBlur={() =>
                  void patchTavily({
                    ...(tavilyCfg || { enabled: false, transport: 'stdio' }),
                    args: tavilyArgsDraft.split(' ').filter(Boolean),
                  })
                }
                fullWidth
                disabled={busy}
                placeholder="-y mcp-remote https://…"
              />
              <TextField
                size="small"
                label="env (JSON object)"
                value={tavilyEnvText}
                onChange={(e) => {
                  setTavilyEnvDraft(e.target.value)
                  setTavilyEnvError(null)
                }}
                onBlur={() => {
                  const parsed = normalizeEnvText(tavilyEnvDraft)
                  if (!parsed.ok) {
                    setTavilyEnvError(parsed.error)
                    return
                  }
                  void patchTavily({ ...(tavilyCfg || { enabled: false, transport: 'stdio' }), env: parsed.value })
                }}
                fullWidth
                multiline
                minRows={4}
                disabled={busy}
                inputProps={{ style: { fontFamily: 'monospace' } }}
              />
              {tavilyEnvError && <Alert severity="warning">{tavilyEnvError}</Alert>}
            </>
          )}

          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => void handleTestTavily()}
              disabled={busy || !tavilyEnabled || tavilyTransport !== 'sse' || !(tavilyCfg?.url || '').trim()}
            >
              Test Connection
            </Button>
          </Stack>
        </Stack>
      </Paper>

      <McpConsolePanel servers={serverOptions} disabled={busy} defaultServerId="kite" />

      {advancedOpen && (
        <McpJsonConfigEditor
          onApplied={() => {
            void load()
          }}
        />
      )}

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

      <Dialog open={authOpen} onClose={() => setAuthOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Kite MCP Authorization</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 1 }}>
            This authorization flow is handled by Kite MCP. SigmaTrader never sees your broker password.
          </Alert>
          {authWarning ? (
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
              {authWarning}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No details.
            </Typography>
          )}
          {authUrl && (
            <Box sx={{ pt: 2 }}>
              <TextField label="Login URL" size="small" value={authUrl} fullWidth inputProps={{ readOnly: true }} />
              <Stack direction="row" spacing={1} sx={{ pt: 1, flexWrap: 'wrap' }}>
                <Button size="small" variant="outlined" onClick={() => window.open(authUrl, '_blank', 'noopener')}>
                  Open login link
                </Button>
                <Button size="small" variant="outlined" onClick={() => void refreshKiteLiveStatus()}>
                  I completed login → check status
                </Button>
              </Stack>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAuthOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
