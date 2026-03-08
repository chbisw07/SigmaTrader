import { useEffect, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import { fetchMcpJsonConfig, updateMcpJsonConfig } from '../../services/mcpServers'

function tryParseJson(text: string): { ok: true; value: any } | { ok: false; error: string } {
  try {
    const v = JSON.parse(text || '{}')
    if (v === null || typeof v !== 'object' || Array.isArray(v)) {
      return { ok: false, error: 'Config must be a JSON object.' }
    }
    return { ok: true, value: v }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Invalid JSON' }
  }
}

export function McpJsonConfigEditor({ onApplied }: { onApplied?: () => void }) {
  const [text, setText] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const load = async () => {
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await fetchMcpJsonConfig()
      setText(JSON.stringify(res.config ?? {}, null, 2))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load config')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const apply = async () => {
    setBusy(true)
    setError(null)
    setSuccess(null)
    const parsed = tryParseJson(text)
    if (!parsed.ok) {
      setBusy(false)
      setError(parsed.error)
      return
    }
    try {
      const res = await updateMcpJsonConfig(parsed.value)
      setText(JSON.stringify(res.config ?? {}, null, 2))
      setSuccess('Applied.')
      onApplied?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to apply config')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6">Advanced JSON configuration (mcp.json)</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ pt: 0.5 }}>
        Edit MCP servers as JSON (LM Studio-style `mcpServers` or VS Code-style `servers`). SigmaTrader currently supports
        remote SSE servers; stdio/server processes are stored for future use.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mt: 1.5 }}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mt: 1.5 }}>
          {success}
        </Alert>
      )}

      <Box sx={{ pt: 1.5 }}>
        <TextField
          label="mcp.json"
          value={text}
          onChange={(e) => setText(e.target.value)}
          fullWidth
          multiline
          minRows={12}
          inputProps={{ style: { fontFamily: 'monospace' } }}
          disabled={busy}
        />
      </Box>

      <Stack direction="row" spacing={1} sx={{ pt: 1.5, flexWrap: 'wrap' }}>
        <Button size="small" variant="outlined" onClick={() => void load()} disabled={busy}>
          Reload
        </Button>
        <Button size="small" variant="contained" onClick={() => void apply()} disabled={busy}>
          Apply
        </Button>
      </Stack>
    </Paper>
  )
}

