import { useEffect, useMemo, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import {
  createAiKey,
  deleteAiKey,
  discoverAiModels,
  fetchAiConfig,
  fetchAiProviders,
  listAiKeys,
  runAiTest,
  updateAiConfig,
  updateAiKey,
  type AiActiveConfig,
  type AiProviderKey,
  type ModelEntry,
  type ProviderDescriptor,
} from '../../services/aiProvider'

type KeyModalMode = 'create' | 'edit'

function canRunTest(cfg: AiActiveConfig, p?: ProviderDescriptor | null): { ok: boolean; reason?: string } {
  const provider = p?.id ?? cfg.provider
  const requiresKey = Boolean(p?.requires_api_key)
  const supportsBaseUrl = Boolean(p?.supports_base_url)

  if (!cfg.enabled) return { ok: false, reason: 'Enable provider first.' }
  if (!provider) return { ok: false, reason: 'Select a provider.' }
  if (!cfg.model) return { ok: false, reason: 'Select a model.' }
  if (supportsBaseUrl && !cfg.base_url) return { ok: false, reason: 'Base URL is required.' }
  if (requiresKey && !cfg.active_key_id) return { ok: false, reason: 'API key is required.' }
  return { ok: true }
}

export function AiProviderSettingsPanel() {
  const [providers, setProviders] = useState<ProviderDescriptor[]>([])
  const [cfg, setCfg] = useState<AiActiveConfig | null>(null)
  const [keys, setKeys] = useState<AiProviderKey[]>([])
  const [models, setModels] = useState<ModelEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [modelsBusy, setModelsBusy] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)

  const [testPrompt, setTestPrompt] = useState('Say OK and current time in one line.')
  const [testBusy, setTestBusy] = useState(false)
  const [testError, setTestError] = useState<string | null>(null)
  const [testOutput, setTestOutput] = useState<{ text: string; latency_ms: number; usage?: any } | null>(null)

  const [keyModalOpen, setKeyModalOpen] = useState(false)
  const [keyModalMode, setKeyModalMode] = useState<KeyModalMode>('create')
  const [keyModalId, setKeyModalId] = useState<number | null>(null)
  const [keyNameDraft, setKeyNameDraft] = useState('')
  const [keyValueDraft, setKeyValueDraft] = useState('')

  const providerInfo = useMemo(() => {
    if (!cfg) return null
    return providers.find((p) => p.id === cfg.provider) ?? null
  }, [providers, cfg])

  const load = async () => {
    setError(null)
    try {
      const [ps, c] = await Promise.all([fetchAiProviders(), fetchAiConfig()])
      setProviders(ps)
      setCfg(c)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load AI provider config')
    }
  }

  const refreshKeys = async (providerId: string) => {
    try {
      const rows = await listAiKeys(providerId)
      setKeys(rows)
    } catch (e) {
      setKeys([])
      setError(e instanceof Error ? e.message : 'Failed to load keys')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    if (!cfg?.provider) return
    void refreshKeys(cfg.provider)
  }, [cfg?.provider])

  const patch = async (partial: Partial<AiActiveConfig>) => {
    if (!cfg) return
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const next = await updateAiConfig(partial as any)
      setCfg(next)
      setSuccess('Saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  const handleProviderChange = async (providerId: string) => {
    const p = providers.find((x) => x.id === providerId) ?? null
    setModels([])
    setModelsError(null)
    setTestOutput(null)
    setTestError(null)
    await patch({
      provider: providerId,
      base_url: p?.supports_base_url ? (p.default_base_url ?? null) : null,
      active_key_id: null,
      model: null,
    } as any)
  }

  const openCreateKey = () => {
    setKeyModalMode('create')
    setKeyModalId(null)
    setKeyNameDraft('')
    setKeyValueDraft('')
    setKeyModalOpen(true)
  }

  const openEditKey = () => {
    if (!cfg?.active_key_id) return
    const row = keys.find((k) => k.id === cfg.active_key_id) ?? null
    setKeyModalMode('edit')
    setKeyModalId(cfg.active_key_id)
    setKeyNameDraft(row?.key_name ?? '')
    setKeyValueDraft('')
    setKeyModalOpen(true)
  }

  const saveKey = async () => {
    if (!cfg) return
    const providerId = cfg.provider
    const name = keyNameDraft.trim()
    const value = keyValueDraft
    setBusy(true)
    setError(null)
    try {
      if (keyModalMode === 'create') {
        const created = await createAiKey({
          provider: providerId,
          key_name: name,
          api_key_value: value,
        })
        await refreshKeys(providerId)
        await patch({ active_key_id: created.id } as any)
      } else if (keyModalMode === 'edit' && keyModalId) {
        await updateAiKey(keyModalId, {
          key_name: name || undefined,
          api_key_value: value ? value : undefined,
        })
        await refreshKeys(providerId)
      }
      setKeyModalOpen(false)
      setKeyValueDraft('')
      setSuccess('Key saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save key')
    } finally {
      setBusy(false)
    }
  }

  const removeKey = async () => {
    if (!cfg?.active_key_id) return
    const id = cfg.active_key_id
    if (!window.confirm('Delete this API key? This cannot be undone.')) return
    setBusy(true)
    setError(null)
    try {
      await deleteAiKey(id)
      await refreshKeys(cfg.provider)
      await patch({ active_key_id: null } as any)
      setSuccess('Key deleted.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete key')
    } finally {
      setBusy(false)
    }
  }

  const fetchModels = async () => {
    if (!cfg) return
    setModelsBusy(true)
    setModelsError(null)
    try {
      const ms = await discoverAiModels({
        provider: cfg.provider,
        base_url: cfg.base_url ?? null,
        key_id: cfg.active_key_id ?? null,
      })
      setModels(ms)
      if (ms.length === 0) setModelsError('No models returned. Enter a custom model name.')
    } catch (e) {
      setModels([])
      setModelsError(e instanceof Error ? e.message : 'Failed to fetch models')
    } finally {
      setModelsBusy(false)
    }
  }

  const doTest = async () => {
    if (!cfg) return
    setTestBusy(true)
    setTestError(null)
    setTestOutput(null)
    try {
      const out = await runAiTest({
        provider: cfg.provider,
        model: cfg.model ?? '',
        base_url: cfg.base_url ?? null,
        key_id: cfg.active_key_id ?? null,
        prompt: testPrompt,
      })
      setTestOutput(out)
    } catch (e) {
      setTestError(e instanceof Error ? e.message : 'Test failed')
    } finally {
      setTestBusy(false)
    }
  }

  if (!cfg) {
    return (
      <Box>
        <Typography variant="subtitle1">Model / Provider</Typography>
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

  const ready = canRunTest(cfg, providerInfo)

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
        <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 200 }}>
          Model / Provider
        </Typography>
        <Button size="small" variant="outlined" onClick={() => void load()} disabled={busy}>
          Refresh
        </Button>
      </Stack>

      <Typography variant="body2" color="text.secondary" sx={{ pt: 0.5 }}>
        Configure an AI provider and run a test prompt from inside SigmaTrader. API keys are stored server-side and never
        returned to the browser.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mt: 1 }}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mt: 1 }}>
          {success}
        </Alert>
      )}

      <Stack spacing={1.5} sx={{ pt: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={cfg.enabled}
              onChange={(_, v) => void patch({ enabled: v } as any)}
              disabled={busy}
            />
          }
          label="Provider enabled (allows model discovery + test)"
        />

        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          <TextField
            label="Provider"
            select
            size="small"
            value={cfg.provider}
            onChange={(e) => void handleProviderChange(e.target.value)}
            sx={{ width: 240 }}
          >
            {providers.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.label}
              </MenuItem>
            ))}
          </TextField>

          {providerInfo?.supports_base_url && (
            <TextField
              label="Base URL"
              size="small"
              value={cfg.base_url ?? ''}
              onChange={(e) => setCfg((prev) => (prev ? { ...prev, base_url: e.target.value } : prev))}
              onBlur={() => void patch({ base_url: cfg.base_url ?? null } as any)}
              sx={{ minWidth: 320, flex: 1 }}
              placeholder={providerInfo.default_base_url ?? ''}
            />
          )}
        </Stack>

        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            label="API key"
            select
            size="small"
            value={cfg.active_key_id ?? ''}
            onChange={(e) => void patch({ active_key_id: e.target.value ? Number(e.target.value) : null } as any)}
            sx={{ minWidth: 260, flex: 1 }}
            disabled={busy || !providerInfo?.requires_api_key}
            helperText={providerInfo?.requires_api_key ? 'Select a saved key (masked).' : 'No key required for this provider.'}
          >
            <MenuItem value="">(none)</MenuItem>
            {keys.map((k) => (
              <MenuItem key={k.id} value={k.id}>
                {k.key_name} • {k.key_masked}
              </MenuItem>
            ))}
          </TextField>
          <Button size="small" variant="outlined" onClick={openCreateKey} disabled={busy || !providerInfo?.requires_api_key}>
            Add key
          </Button>
          <Button size="small" variant="outlined" onClick={openEditKey} disabled={busy || !cfg.active_key_id}>
            Edit
          </Button>
          <Button size="small" color="error" variant="outlined" onClick={() => void removeKey()} disabled={busy || !cfg.active_key_id}>
            Delete
          </Button>
        </Stack>

        <Divider />

        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            label="Model"
            select={models.length > 0}
            size="small"
            value={cfg.model ?? ''}
            onChange={(e) => void patch({ model: e.target.value || null } as any)}
            sx={{ minWidth: 300, flex: 1 }}
            placeholder={models.length === 0 ? 'Enter model name (custom)' : undefined}
          >
            {models.length > 0 ? (
              [
                <MenuItem key="none" value="">
                  (none)
                </MenuItem>,
                ...models.map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    {m.label}
                  </MenuItem>
                )),
              ]
            ) : (
              undefined
            )}
          </TextField>
          <Button
            size="small"
            variant="outlined"
            onClick={() => void fetchModels()}
            disabled={modelsBusy || busy || !cfg.enabled}
          >
            {modelsBusy ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={16} />
                <span>Fetching…</span>
              </Stack>
            ) : (
              'Fetch models'
            )}
          </Button>
        </Stack>

        {modelsError && <Alert severity="warning">{modelsError}</Alert>}

        <Divider />

        <FormControlLabel
          control={
            <Switch
              checked={cfg.do_not_send_pii}
              onChange={(_, v) => void patch({ do_not_send_pii: v } as any)}
              disabled={busy}
            />
          }
          label="PII-safe mode (remote LLM sees summaries only)"
        />
        <Typography variant="caption" color="text.secondary" sx={{ mt: -0.5 }}>
          Remote providers never receive raw broker payloads. Local providers may support deeper context later behind an
          explicit toggle.
        </Typography>

        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          <TextField
            label="Max tokens / request"
            type="number"
            size="small"
            value={cfg.limits.max_tokens_per_request ?? ''}
            onChange={(e) =>
              void patch({
                limits: {
                  ...cfg.limits,
                  max_tokens_per_request: e.target.value ? Number(e.target.value) : null,
                },
              } as any)
            }
            sx={{ width: 200 }}
          />
          <TextField
            label="Max cost / request (USD)"
            type="number"
            size="small"
            value={cfg.limits.max_cost_usd_per_request ?? ''}
            onChange={(e) =>
              void patch({
                limits: {
                  ...cfg.limits,
                  max_cost_usd_per_request: e.target.value ? Number(e.target.value) : null,
                },
              } as any)
            }
            sx={{ width: 220 }}
          />
          <TextField
            label="Max cost / day (USD)"
            type="number"
            size="small"
            value={cfg.limits.max_cost_usd_per_day ?? ''}
            onChange={(e) =>
              void patch({
                limits: {
                  ...cfg.limits,
                  max_cost_usd_per_day: e.target.value ? Number(e.target.value) : null,
                },
              } as any)
            }
            sx={{ width: 220 }}
          />
        </Stack>

        <Divider />

        <Typography variant="subtitle2">Test Prompt</Typography>
        {!ready.ok && <Alert severity="info">{ready.reason}</Alert>}
        <TextField
          label="Prompt"
          size="small"
          multiline
          minRows={3}
          value={testPrompt}
          onChange={(e) => setTestPrompt(e.target.value)}
          fullWidth
        />
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <Button
            size="small"
            variant="contained"
            onClick={() => void doTest()}
            disabled={testBusy || busy || !ready.ok}
          >
            {testBusy ? 'Running…' : 'Run Test'}
          </Button>
          {testOutput && (
            <Typography variant="caption" color="text.secondary">
              Latency: {testOutput.latency_ms}ms • Tokens: {testOutput.usage?.total_tokens ?? 'n/a'}
            </Typography>
          )}
        </Stack>
        {testError && <Alert severity="error">{testError}</Alert>}
        {testOutput && (
          <Paper variant="outlined" sx={{ p: 1, bgcolor: 'background.default' }}>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
              {testOutput.text}
            </Typography>
          </Paper>
        )}
      </Stack>

      <Dialog open={keyModalOpen} onClose={() => setKeyModalOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{keyModalMode === 'create' ? 'Add API key' : 'Edit API key'}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The key value is stored server-side and never shown again after saving.
          </Typography>
          <Stack spacing={1.25}>
            <TextField
              autoFocus
              label="Key name"
              size="small"
              value={keyNameDraft}
              onChange={(e) => setKeyNameDraft(e.target.value)}
              fullWidth
            />
            <TextField
              label={keyModalMode === 'create' ? 'API key' : 'API key (leave blank to keep unchanged)'}
              size="small"
              type="password"
              value={keyValueDraft}
              onChange={(e) => setKeyValueDraft(e.target.value)}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setKeyModalOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => void saveKey()}
            disabled={busy || !keyNameDraft.trim() || (keyModalMode === 'create' && !keyValueDraft.trim())}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  )
}
