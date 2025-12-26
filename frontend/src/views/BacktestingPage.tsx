import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { MarkdownLite } from '../components/MarkdownLite'
import { fetchHoldings } from '../services/positions'
import { fetchGroup, listGroups, type Group, type GroupDetail } from '../services/groups'
import {
  createBacktestRun,
  getBacktestRun,
  listBacktestRuns,
  type BacktestKind,
  type BacktestRun,
} from '../services/backtests'

import backtestingHelpText from '../../../docs/backtesting_page_help.md?raw'

type UniverseMode = 'HOLDINGS' | 'GROUP' | 'BOTH'

type BacktestTab = 'SIGNAL' | 'PORTFOLIO' | 'EXECUTION'

function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function addDays(d: Date, days: number): Date {
  const out = new Date(d)
  out.setDate(out.getDate() + days)
  return out
}

function getDatePreset(preset: '6M' | '1Y' | '2Y'): { start: string; end: string } {
  const end = new Date()
  const start =
    preset === '6M' ? addDays(end, -182) : preset === '1Y' ? addDays(end, -365) : addDays(end, -730)
  return { start: toIsoDate(start), end: toIsoDate(end) }
}

export function BacktestingPage() {
  const [tab, setTab] = useState<BacktestTab>('SIGNAL')
  const kind: BacktestKind = tab

  const [helpOpen, setHelpOpen] = useState(false)

  const [groups, setGroups] = useState<Group[]>([])
  const [universeMode, setUniverseMode] = useState<UniverseMode>('GROUP')
  const [brokerName, setBrokerName] = useState<'zerodha' | 'angelone'>('zerodha')
  const [groupId, setGroupId] = useState<number | ''>('')
  const [groupDetail, setGroupDetail] = useState<GroupDetail | null>(null)

  const preset = useMemo(() => getDatePreset('1Y'), [])
  const [startDate, setStartDate] = useState(preset.start)
  const [endDate, setEndDate] = useState(preset.end)

  const [runs, setRuns] = useState<BacktestRun[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const refreshRuns = useCallback(async () => {
    setRunsLoading(true)
    try {
      const data = await listBacktestRuns({ kind, limit: 50 })
      setRuns(data)
    } finally {
      setRunsLoading(false)
    }
  }, [kind])

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const data = await listGroups().catch(() => [])
        if (!active) return
        setGroups(data)
      } catch {
        if (!active) return
        setGroups([])
      }
    })()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    void refreshRuns()
  }, [refreshRuns])

  useEffect(() => {
    let active = true
    void (async () => {
      if (!groupId || typeof groupId !== 'number') {
        setGroupDetail(null)
        return
      }
      try {
        const detail = await fetchGroup(groupId)
        if (!active) return
        setGroupDetail(detail)
      } catch {
        if (!active) return
        setGroupDetail(null)
      }
    })()
    return () => {
      active = false
    }
  }, [groupId])

  useEffect(() => {
    let active = true
    void (async () => {
      if (selectedRunId == null) {
        setSelectedRun(null)
        return
      }
      try {
        const run = await getBacktestRun(selectedRunId)
        if (!active) return
        setSelectedRun(run)
      } catch (err) {
        if (!active) return
        setSelectedRun(null)
        setError(err instanceof Error ? err.message : 'Failed to load run')
      }
    })()
    return () => {
      active = false
    }
  }, [selectedRunId])

  const buildUniverseSymbols = useCallback(async () => {
    const symSet = new Map<string, { symbol: string; exchange: string }>()
    const add = (symbol: string, exchange: string) => {
      const s = symbol.trim().toUpperCase()
      const e = (exchange || 'NSE').trim().toUpperCase()
      if (!s) return
      symSet.set(`${e}:${s}`, { symbol: s, exchange: e })
    }

    if (universeMode === 'HOLDINGS' || universeMode === 'BOTH') {
      const holdings = await fetchHoldings(brokerName)
      for (const h of holdings) {
        add(h.symbol, h.exchange ?? 'NSE')
      }
    }
    if (universeMode === 'GROUP' || universeMode === 'BOTH') {
      if (groupDetail) {
        for (const m of groupDetail.members ?? []) {
          add(m.symbol, m.exchange ?? 'NSE')
        }
      }
    }
    return Array.from(symSet.values())
  }, [brokerName, groupDetail, universeMode])

  const handleRun = async () => {
    setError(null)
    setRunning(true)
    try {
      const symbols = await buildUniverseSymbols()
      const title = `${kind} backtest`
      const run = await createBacktestRun({
        kind,
        title,
        universe: {
          mode: universeMode,
          broker_name: brokerName,
          group_id: typeof groupId === 'number' ? groupId : null,
          symbols,
        },
        config: {
          timeframe: '1d',
          start_date: startDate,
          end_date: endDate,
          preset: {
            note: 'Backtesting engine will be implemented in subsequent tasks.',
          },
        },
      })
      setSelectedRunId(run.id)
      await refreshRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  const runColumns = useMemo((): GridColDef[] => {
    const cols: GridColDef[] = [
      { field: 'id', headerName: 'Run', width: 90 },
      { field: 'created_at', headerName: 'Created', width: 180 },
      { field: 'status', headerName: 'Status', width: 120 },
      { field: 'title', headerName: 'Title', flex: 1, minWidth: 180 },
    ]
    return cols
  }, [])

  const selectedUniverseSummary = useMemo(() => {
    if (universeMode === 'HOLDINGS') return `Holdings (${brokerName})`
    if (universeMode === 'GROUP') return groupDetail ? `Group: ${groupDetail.name}` : 'Group: (select)'
    const groupLabel = groupDetail ? groupDetail.name : '(select group)'
    return `Both: Holdings (${brokerName}) + ${groupLabel}`
  }, [brokerName, groupDetail, universeMode])

  return (
    <Box sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="h5">Backtesting</Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Help">
          <IconButton size="small" onClick={() => setHelpOpen(true)}>
            <HelpOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>

      <Tabs value={tab} onChange={(_e, v) => setTab(v as BacktestTab)} sx={{ mt: 1 }}>
        <Tab value="SIGNAL" label="Signal backtest" />
        <Tab value="PORTFOLIO" label="Portfolio backtest" />
        <Tab value="EXECUTION" label="Execution backtest" />
      </Tabs>

      <Box
        sx={{
          mt: 2,
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '420px 1fr' },
          gap: 2,
          alignItems: 'start',
        }}
      >
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1">Inputs</Typography>

            <FormControl fullWidth size="small">
              <InputLabel id="bt-universe-label">Universe</InputLabel>
              <Select
                labelId="bt-universe-label"
                label="Universe"
                value={universeMode}
                onChange={(e) => setUniverseMode(e.target.value as UniverseMode)}
              >
                <MenuItem value="HOLDINGS">Holdings</MenuItem>
                <MenuItem value="GROUP">Group</MenuItem>
                <MenuItem value="BOTH">Both</MenuItem>
              </Select>
            </FormControl>

            {(universeMode === 'HOLDINGS' || universeMode === 'BOTH') && (
              <FormControl fullWidth size="small">
                <InputLabel id="bt-broker-label">Broker</InputLabel>
                <Select
                  labelId="bt-broker-label"
                  label="Broker"
                  value={brokerName}
                  onChange={(e) =>
                    setBrokerName(e.target.value === 'angelone' ? 'angelone' : 'zerodha')
                  }
                >
                  <MenuItem value="zerodha">Zerodha</MenuItem>
                  <MenuItem value="angelone">AngelOne</MenuItem>
                </Select>
              </FormControl>
            )}

            {(universeMode === 'GROUP' || universeMode === 'BOTH') && (
              <FormControl fullWidth size="small">
                <InputLabel id="bt-group-label">Group</InputLabel>
                <Select
                  labelId="bt-group-label"
                  label="Group"
                  value={groupId}
                  onChange={(e) => setGroupId(e.target.value === '' ? '' : Number(e.target.value))}
                >
                  <MenuItem value="">(select)</MenuItem>
                  {groups.map((g) => (
                    <MenuItem key={g.id} value={String(g.id)}>
                      {g.name} ({g.kind})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Chip size="small" label={selectedUniverseSummary} />
              {groupDetail && (universeMode === 'GROUP' || universeMode === 'BOTH') && (
                <Chip size="small" variant="outlined" label={`${groupDetail.members.length} symbols`} />
              )}
            </Stack>

            <Stack direction="row" spacing={1}>
              <TextField
                label="Start"
                type="date"
                size="small"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
              <TextField
                label="End"
                type="date"
                size="small"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
            </Stack>

            <Stack direction="row" spacing={1} flexWrap="wrap">
              {(['6M', '1Y', '2Y'] as const).map((p) => (
                <Button
                  key={p}
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    const r = getDatePreset(p)
                    setStartDate(r.start)
                    setEndDate(r.end)
                  }}
                >
                  {p}
                </Button>
              ))}
              <Box sx={{ flexGrow: 1 }} />
              <Button variant="contained" onClick={() => void handleRun()} disabled={running}>
                {running ? 'Running…' : 'Run backtest'}
              </Button>
            </Stack>

            {error && (
              <Typography variant="body2" color="error">
                {error}
              </Typography>
            )}

            <Typography variant="caption" color="text.secondary">
              Foundation note: this sprint adds the Backtesting workspace and run history. Strategy engines are implemented in subsequent tasks.
            </Typography>
          </Stack>
        </Paper>

        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="subtitle1">Results</Typography>
              <Box sx={{ flexGrow: 1 }} />
              <Button size="small" variant="outlined" onClick={() => void refreshRuns()} disabled={runsLoading}>
                Refresh runs
              </Button>
            </Stack>

            <Box sx={{ height: 260 }}>
              <DataGrid
                rows={runs}
                columns={runColumns}
                getRowId={(r) => (r as BacktestRun).id}
                loading={runsLoading}
                density="compact"
                disableRowSelectionOnClick
                onRowClick={(p) => setSelectedRunId((p.row as BacktestRun).id)}
                initialState={{
                  pagination: { paginationModel: { pageSize: 5 } },
                }}
                pageSizeOptions={[5, 10, 25]}
              />
            </Box>

            <DividerBlock title="Selected run" />
            {selectedRun ? (
              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
                <Typography variant="body2" color="text.secondary">
                  Run #{selectedRun.id} • {selectedRun.kind} • {selectedRun.status}
                </Typography>
                <pre style={{ margin: 0, fontSize: 12, overflow: 'auto' }}>
                  {JSON.stringify(selectedRun, null, 2)}
                </pre>
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      const config = selectedRun.config as Record<string, unknown>
                      const runKind = (selectedRun.kind || kind) as BacktestKind
                      void (async () => {
                        setError(null)
                        setRunning(true)
                        try {
                          const universe = (config.universe ?? {}) as Record<string, unknown>
                          const run = await createBacktestRun({
                            kind: runKind,
                            title: selectedRun.title ?? `${runKind} backtest`,
                            universe: {
                              mode: (universe.mode as UniverseMode) ?? 'GROUP',
                              broker_name:
                                universe.broker_name === 'angelone' ? 'angelone' : 'zerodha',
                              group_id:
                                typeof universe.group_id === 'number' ? universe.group_id : null,
                              symbols: Array.isArray(universe.symbols)
                                ? (universe.symbols as Array<Record<string, unknown>>).map((s) => ({
                                    symbol: String(s.symbol ?? '').toUpperCase(),
                                    exchange: String(s.exchange ?? 'NSE').toUpperCase(),
                                  }))
                                : [],
                            },
                            config: (config.config ?? {}) as Record<string, unknown>,
                          })
                          setSelectedRunId(run.id)
                          await refreshRuns()
                        } catch (err) {
                          setError(err instanceof Error ? err.message : 'Failed to rerun')
                        } finally {
                          setRunning(false)
                        }
                      })()
                    }}
                  >
                    Rerun
                  </Button>
                </Stack>
              </Paper>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Select a run to view details.
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>

      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Backtesting help</DialogTitle>
        <DialogContent>
          <MarkdownLite text={backtestingHelpText} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

function DividerBlock({ title }: { title: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ flex: 1, height: 1, bgcolor: 'divider' }} />
      <Typography variant="caption" color="text.secondary">
        {title}
      </Typography>
      <Box sx={{ flex: 1, height: 1, bgcolor: 'divider' }} />
    </Box>
  )
}
