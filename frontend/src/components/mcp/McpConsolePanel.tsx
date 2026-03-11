import { useEffect, useMemo, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import { callMcpTool, listMcpTools, type McpTool } from '../../services/mcpServers'

type ServerOption = { id: string; label: string; enabled: boolean; configured: boolean }

function tryParseJson(text: string): { ok: true; value: any } | { ok: false; error: string } {
  try {
    const v = JSON.parse(text || '{}')
    if (v === null || typeof v !== 'object' || Array.isArray(v)) {
      return { ok: false, error: 'Arguments must be a JSON object.' }
    }
    return { ok: true, value: v }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Invalid JSON' }
  }
}

export function McpConsolePanel({
  servers,
  disabled,
  defaultServerId,
}: {
  servers: ServerOption[]
  disabled?: boolean
  defaultServerId?: string
}) {
  const availableServers = useMemo(() => {
    return (servers || []).filter((s) => Boolean(s.enabled && s.configured))
  }, [servers])

  const [serverId, setServerId] = useState<string>(() => {
    const first = availableServers[0]?.id
    return defaultServerId && availableServers.some((s) => s.id === defaultServerId)
      ? defaultServerId
      : first || ''
  })

  useEffect(() => {
    if (!serverId && availableServers[0]?.id) setServerId(availableServers[0].id)
  }, [availableServers, serverId])

  const [tools, setTools] = useState<McpTool[]>([])
  const [toolsBusy, setToolsBusy] = useState(false)
  const [toolsError, setToolsError] = useState<string | null>(null)

  const [toolName, setToolName] = useState<string>('tools/list')
  const [argsText, setArgsText] = useState<string>('{}')
  const [runBusy, setRunBusy] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [output, setOutput] = useState<any>(null)

  const toolOptions = useMemo(() => {
    const names = tools.map((t) => t.name)
    return names.sort()
  }, [tools])

  const loadTools = async () => {
    if (!serverId) return
    setToolsBusy(true)
    setToolsError(null)
    try {
      const rows = await listMcpTools(serverId)
      setTools(rows)
      if (rows.length > 0 && !rows.some((t) => t.name === toolName)) {
        setToolName(rows[0].name)
      }
    } catch (e) {
      setTools([])
      setToolsError(e instanceof Error ? e.message : 'Failed to list tools')
    } finally {
      setToolsBusy(false)
    }
  }

  useEffect(() => {
    if (!serverId) return
    void loadTools()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId])

  const run = async () => {
    if (!serverId) return
    setRunBusy(true)
    setRunError(null)
    setOutput(null)
    const parsed = tryParseJson(argsText)
    if (!parsed.ok) {
      setRunBusy(false)
      setRunError(parsed.error)
      return
    }
    try {
      const res = await callMcpTool({ serverId, name: toolName, arguments: parsed.value })
      setOutput(res)
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'Tool call failed')
    } finally {
      setRunBusy(false)
    }
  }

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6">Tool discovery & test console</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ pt: 0.5 }}>
        List tools and run `tools/call` with JSON arguments. Responses are shown verbatim.
      </Typography>

      {availableServers.length === 0 && (
        <Alert severity="info" sx={{ mt: 1 }}>
          No enabled + configured MCP servers yet. Enable a server and configure its URL first.
        </Alert>
      )}

      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', pt: 1.5 }} alignItems="center">
        <TextField
          label="Server"
          select
          size="small"
          value={serverId}
          onChange={(e) => setServerId(e.target.value)}
          sx={{ minWidth: 240 }}
          disabled={disabled || availableServers.length === 0}
        >
          {availableServers.length === 0 ? (
            <MenuItem value="">(no servers)</MenuItem>
          ) : (
            availableServers.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.label}
              </MenuItem>
            ))
          )}
        </TextField>

        <Button size="small" variant="outlined" onClick={() => void loadTools()} disabled={disabled || toolsBusy || !serverId}>
          {toolsBusy ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={16} />
              <span>Loading…</span>
            </Stack>
          ) : (
            'Refresh tools'
          )}
        </Button>
      </Stack>

      {toolsError && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          {toolsError}
        </Alert>
      )}

      <Box sx={{ pt: 1.5 }}>
        <TextField
          label="Tool"
          select
          size="small"
          value={toolName}
          onChange={(e) => setToolName(e.target.value)}
          fullWidth
          disabled={disabled || toolOptions.length === 0 || !serverId}
        >
          {toolOptions.length === 0 ? (
            <MenuItem value="tools/list">(no tools)</MenuItem>
          ) : (
            toolOptions.map((n) => (
              <MenuItem key={n} value={n}>
                {n}
              </MenuItem>
            ))
          )}
        </TextField>
      </Box>

      <Box sx={{ pt: 1.5 }}>
        <TextField
          label="Arguments (JSON object)"
          size="small"
          multiline
          minRows={4}
          value={argsText}
          onChange={(e) => setArgsText(e.target.value)}
          fullWidth
          disabled={disabled || !serverId}
          placeholder="{}"
          inputProps={{ style: { fontFamily: 'monospace' } }}
        />
      </Box>

      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', pt: 1.5 }} alignItems="center">
        <Button size="small" variant="contained" onClick={() => void run()} disabled={disabled || runBusy || !serverId}>
          {runBusy ? 'Running…' : 'Run tool'}
        </Button>
      </Stack>

      {runError && (
        <Alert severity="error" sx={{ mt: 1 }}>
          {runError}
        </Alert>
      )}

      {output && (
        <Paper variant="outlined" sx={{ p: 1, mt: 1.5, bgcolor: 'background.paper' }}>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(output, null, 2)}
          </Typography>
        </Paper>
      )}
    </Paper>
  )
}

