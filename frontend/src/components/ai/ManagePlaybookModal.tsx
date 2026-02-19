import { useEffect, useState } from 'react'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import FormControlLabel from '@mui/material/FormControlLabel'

import { fetchManagePlaybook, updateManagePlaybook, type ManagePlaybook } from '../../services/aiTradingManager'

export function ManagePlaybookModal(props: {
  open: boolean
  playbookId: string
  onClose: () => void
  onSaved?: () => void
}) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pb, setPb] = useState<ManagePlaybook | null>(null)
  const [exitPolicyText, setExitPolicyText] = useState<string>('{}')
  const [scalePolicyText, setScalePolicyText] = useState<string>('{}')

  useEffect(() => {
    if (!props.open) return
    let active = true
    void (async () => {
      setLoading(true)
      try {
        const row = await fetchManagePlaybook({ playbook_id: props.playbookId })
        if (!active) return
        setPb(row)
        setExitPolicyText(JSON.stringify(row.exit_policy ?? {}, null, 2))
        setScalePolicyText(JSON.stringify(row.scale_policy ?? {}, null, 2))
        setError(null)
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load playbook')
      } finally {
        if (!active) return
        setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [props.open, props.playbookId])

  const handleSave = async () => {
    if (!pb) return
    setSaving(true)
    try {
      const exitPolicy = JSON.parse(exitPolicyText || '{}')
      const scalePolicy = JSON.parse(scalePolicyText || '{}')
      await updateManagePlaybook({
        playbook_id: pb.playbook_id,
        patch: {
          enabled: pb.enabled,
          mode: pb.mode,
          horizon: pb.horizon,
          review_cadence_min: pb.review_cadence_min,
          behavior_on_strategy_exit: pb.behavior_on_strategy_exit,
          exit_policy: exitPolicy,
          scale_policy: scalePolicy,
          notes: pb.notes ?? null,
        },
      })
      setError(null)
      props.onSaved?.()
      props.onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save playbook')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={props.open} onClose={props.onClose} maxWidth="md" fullWidth>
      <DialogTitle>Edit playbook</DialogTitle>
      <DialogContent dividers>
        {error ? (
          <Typography variant="body2" color="error" sx={{ mb: 1 }}>
            {error}
          </Typography>
        ) : null}
        {loading || !pb ? (
          <Typography variant="body2" color="text.secondary">
            Loading…
          </Typography>
        ) : (
          <Stack spacing={1.5}>
            <FormControlLabel
              control={<Switch checked={pb.enabled} onChange={(e) => setPb({ ...pb, enabled: e.target.checked })} />}
              label="AI Managed (enabled)"
            />
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <Typography variant="caption" color="text.secondary">
                  Mode
                </Typography>
                <Select value={pb.mode} onChange={(e) => setPb({ ...pb, mode: String(e.target.value) })}>
                  <MenuItem value="OBSERVE">OBSERVE</MenuItem>
                  <MenuItem value="PROPOSE">PROPOSE</MenuItem>
                  <MenuItem value="EXECUTE">EXECUTE</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <Typography variant="caption" color="text.secondary">
                  Horizon
                </Typography>
                <Select value={pb.horizon} onChange={(e) => setPb({ ...pb, horizon: String(e.target.value) })}>
                  <MenuItem value="INTRADAY">INTRADAY</MenuItem>
                  <MenuItem value="SWING">SWING</MenuItem>
                  <MenuItem value="LONGTERM">LONGTERM</MenuItem>
                </Select>
              </FormControl>
              <TextField
                size="small"
                label="Review cadence (min)"
                value={pb.review_cadence_min}
                onChange={(e) => setPb({ ...pb, review_cadence_min: Number(e.target.value) || 0 })}
                sx={{ maxWidth: 220 }}
              />
              <FormControl size="small" sx={{ minWidth: 240 }}>
                <Typography variant="caption" color="text.secondary">
                  Strategy exit behavior (TV)
                </Typography>
                <Select
                  value={pb.behavior_on_strategy_exit}
                  onChange={(e) => setPb({ ...pb, behavior_on_strategy_exit: String(e.target.value) })}
                >
                  <MenuItem value="ALLOW_AS_IS">ALLOW_AS_IS</MenuItem>
                  <MenuItem value="CONVERT_TO_PARTIAL">CONVERT_TO_PARTIAL</MenuItem>
                  <MenuItem value="REQUIRE_CONFIRMATION">REQUIRE_CONFIRMATION</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            <TextField
              size="small"
              label="Exit policy (JSON)"
              value={exitPolicyText}
              onChange={(e) => setExitPolicyText(e.target.value)}
              fullWidth
              multiline
              minRows={6}
              inputProps={{ style: { fontFamily: 'monospace' } }}
              helperText="Deterministic rules only. RiskGate remains supreme."
            />
            <TextField
              size="small"
              label="Scale policy (JSON)"
              value={scalePolicyText}
              onChange={(e) => setScalePolicyText(e.target.value)}
              fullWidth
              multiline
              minRows={5}
              inputProps={{ style: { fontFamily: 'monospace' } }}
            />
            <TextField
              size="small"
              label="Notes"
              value={pb.notes ?? ''}
              onChange={(e) => setPb({ ...pb, notes: e.target.value })}
              fullWidth
            />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={props.onClose} disabled={saving}>
          Cancel
        </Button>
        <Button variant="contained" onClick={() => void handleSave()} disabled={saving || loading || !pb}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

