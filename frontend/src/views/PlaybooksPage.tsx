import { useEffect, useMemo, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Switch from '@mui/material/Switch'
import FormControlLabel from '@mui/material/FormControlLabel'
import Paper from '@mui/material/Paper'

import { isAiAssistantEnabled } from '../config/aiFeatures'
import {
  createPlaybook,
  createTradePlan,
  fetchPlaybooks,
  runPlaybookNow,
  setPlaybookArmed,
  type Playbook,
  type TradeIntent,
} from '../services/aiTradingManager'

export function PlaybooksPage() {
  const [items, setItems] = useState<Playbook[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [name, setName] = useState('Morning brief (stub)')
  const [symbols, setSymbols] = useState('INFY,SBIN')
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [product, setProduct] = useState<'CNC' | 'MIS'>('CNC')
  const [cadenceSec, setCadenceSec] = useState<number>(60)
  const [authorizationMessageId, setAuthorizationMessageId] = useState<string>('')

  const intent: TradeIntent = useMemo(
    () => ({
      symbols: symbols
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      side,
      product,
      constraints: { qty: 1 },
      risk_budget_pct: 0.5,
    }),
    [symbols, side, product],
  )

  const refresh = async () => {
    setError(null)
    try {
      const rows = await fetchPlaybooks({ account_id: 'default' })
      setItems(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load playbooks')
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const handleCreate = async () => {
    setBusy(true)
    setError(null)
    try {
      const { plan } = await createTradePlan({ account_id: 'default', intent })
      await createPlaybook({
        account_id: 'default',
        name,
        plan,
        cadence_sec: cadenceSec,
      })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create playbook')
    } finally {
      setBusy(false)
    }
  }

  const handleToggleArmed = async (pb: Playbook, armed: boolean) => {
    setBusy(true)
    setError(null)
    try {
      await setPlaybookArmed({
        playbook_id: pb.playbook_id,
        armed,
        authorization_message_id: authorizationMessageId.trim() || undefined,
      })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update arming')
    } finally {
      setBusy(false)
    }
  }

  const handleRunNow = async (pb: Playbook) => {
    setBusy(true)
    setError(null)
    try {
      await runPlaybookNow({
        playbook_id: pb.playbook_id,
        authorization_message_id: authorizationMessageId.trim() || undefined,
      })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run playbook')
    } finally {
      setBusy(false)
    }
  }

  if (!isAiAssistantEnabled()) {
    return (
      <Box>
        <Typography variant="h6">Playbooks</Typography>
        <Typography variant="body2" color="text.secondary">
          AI assistant is disabled.
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h6">Playbooks</Typography>
      <Typography variant="body2" color="text.secondary">
        Phase 2 (arming + cautious automation). Automation executes only when backend flags are enabled.
      </Typography>

      {error && (
        <Typography variant="body2" color="error" sx={{ pt: 1 }}>
          {error}
        </Typography>
      )}

      <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Typography variant="subtitle2">Create playbook</Typography>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          <TextField
            label="Authorization message id (optional)"
            value={authorizationMessageId}
            onChange={(e) => setAuthorizationMessageId(e.target.value)}
            size="small"
            helperText="When execution is enabled, arming/run-now requires a user chat message id."
          />
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} size="small" />
          <TextField
            label="Symbols (comma-separated)"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            size="small"
          />
          <Stack direction="row" spacing={1}>
            <TextField
              label="Side"
              value={side}
              onChange={(e) => setSide((e.target.value as 'BUY' | 'SELL') || 'BUY')}
              size="small"
              sx={{ width: 120 }}
            />
            <TextField
              label="Product"
              value={product}
              onChange={(e) => setProduct((e.target.value as 'CNC' | 'MIS') || 'CNC')}
              size="small"
              sx={{ width: 120 }}
            />
            <TextField
              label="Cadence (sec)"
              type="number"
              value={cadenceSec}
              onChange={(e) => setCadenceSec(Number(e.target.value))}
              size="small"
              sx={{ width: 160 }}
            />
          </Stack>
          <Button onClick={handleCreate} disabled={busy || !name.trim()} variant="contained">
            Create
          </Button>
        </Stack>
      </Paper>

      <Divider sx={{ my: 2 }} />

      <Stack spacing={1}>
        {items.map((pb) => (
          <Paper key={pb.playbook_id} variant="outlined" sx={{ p: 2 }}>
            <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between">
              <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle1" noWrap>
              {pb.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {pb.playbook_id} • plan {pb.plan_id}
            </Typography>
            {pb.armed && !pb.armed_by_message_id && (
              <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>
                Armed without authorization message id (execution will stay dry-run)
              </Typography>
            )}
          </Box>
              <Stack direction="row" spacing={1} alignItems="center">
                <FormControlLabel
                  control={<Switch checked={pb.armed} onChange={(_, v) => void handleToggleArmed(pb, v)} />}
                  label="Armed"
                />
                <Button onClick={() => void handleRunNow(pb)} disabled={busy} variant="outlined">
                  Run now
                </Button>
              </Stack>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ pt: 1 }}>
              Next run: {pb.next_run_at ?? '—'} • Last run: {pb.last_run_at ?? '—'}
            </Typography>
          </Paper>
        ))}
        {items.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No playbooks yet.
          </Typography>
        )}
      </Stack>
    </Box>
  )
}
