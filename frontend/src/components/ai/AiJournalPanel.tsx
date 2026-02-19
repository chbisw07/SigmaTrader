import { useEffect, useMemo, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Chip from '@mui/material/Chip'

import {
  fetchCoverageShadows,
  fetchJournalEvents,
  fetchJournalForecasts,
  fetchLatestPostmortem,
  upsertJournalForecast,
  type JournalEvent,
  type JournalForecast,
  type JournalPostmortem,
  type PositionShadow,
} from '../../services/aiTradingManager'

function fmtNum(v: number | null | undefined, digits = 2) {
  if (v == null || Number.isNaN(v)) return '—'
  return Number(v).toFixed(digits)
}

export function AiJournalPanel(props: { accountId?: string; shadowId?: string | null; onShadowChange?: (id: string) => void }) {
  const accountId = props.accountId ?? 'default'
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [shadows, setShadows] = useState<PositionShadow[]>([])
  const [shadowId, setShadowId] = useState<string>(props.shadowId ?? '')
  const [events, setEvents] = useState<JournalEvent[]>([])
  const [forecasts, setForecasts] = useState<JournalForecast[]>([])
  const [postmortem, setPostmortem] = useState<JournalPostmortem | null>(null)
  const [forecastOutlook, setForecastOutlook] = useState<string>('')
  const [forecastHorizonDays, setForecastHorizonDays] = useState<string>('')
  const [forecastConfidence, setForecastConfidence] = useState<string>('')
  const [forecastThesis, setForecastThesis] = useState<string>('')
  const [savingForecast, setSavingForecast] = useState(false)

  const selectedShadow = useMemo(() => shadows.find((s) => s.shadow_id === shadowId) || null, [shadows, shadowId])

  const loadShadows = async () => {
    const list = await fetchCoverageShadows({ account_id: accountId, status_filter: 'OPEN', unmanaged_only: false, limit: 500 })
    setShadows(list)
    if (!shadowId && list.length) {
      setShadowId(list[0].shadow_id)
      props.onShadowChange?.(list[0].shadow_id)
    }
  }

  const loadAll = async (sid?: string) => {
    const useId = sid ?? shadowId
    if (!useId) return
    const [evs, fcs] = await Promise.all([
      fetchJournalEvents({ shadow_id: useId, limit: 200 }),
      fetchJournalForecasts({ shadow_id: useId, limit: 20 }),
    ])
    setEvents(evs)
    setForecasts(fcs)
    try {
      const pm = await fetchLatestPostmortem({ shadow_id: useId })
      setPostmortem(pm)
    } catch {
      setPostmortem(null)
    }
  }

  useEffect(() => {
    let active = true
    void (async () => {
      setLoading(true)
      try {
        await loadShadows()
        if (!active) return
        await loadAll(props.shadowId ?? shadowId)
        if (!active) return
        setError(null)
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load journal')
      } finally {
        if (!active) return
        setLoading(false)
      }
    })()
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId])

  useEffect(() => {
    if (!shadowId) return
    void (async () => {
      try {
        await loadAll(shadowId)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load journal')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shadowId])

  const handleSelectShadow = (id: string) => {
    setShadowId(id)
    props.onShadowChange?.(id)
  }

  const handleSaveForecast = async () => {
    if (!shadowId) return
    setSavingForecast(true)
    try {
      const outlook = forecastOutlook.trim() ? Number(forecastOutlook) : null
      const horizon = forecastHorizonDays.trim() ? Number(forecastHorizonDays) : null
      const conf = forecastConfidence.trim() ? Number(forecastConfidence) : null
      await upsertJournalForecast({
        position_shadow_id: shadowId,
        author: 'USER',
        outlook_pct: outlook != null && Number.isFinite(outlook) ? outlook : null,
        horizon_days: horizon != null && Number.isFinite(horizon) ? horizon : null,
        confidence: conf != null && Number.isFinite(conf) ? conf : null,
        thesis_text: forecastThesis.trim() || null,
      })
      await loadAll(shadowId)
      setForecastOutlook('')
      setForecastHorizonDays('')
      setForecastConfidence('')
      setForecastThesis('')
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save forecast')
    } finally {
      setSavingForecast(false)
    }
  }

  return (
    <Box sx={{ px: 2, pt: 1, pb: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap">
        <Box>
          <Typography variant="h6">Journal</Typography>
          <Typography variant="caption" color="text.secondary">
            Lightweight intent log + forecasts + postmortems (safe summaries only for remote LLMs).
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Select size="small" value={shadowId} onChange={(e) => handleSelectShadow(String(e.target.value))} sx={{ minWidth: 240 }}>
            {shadows.map((s) => (
              <MenuItem key={s.shadow_id} value={s.shadow_id}>
                {s.symbol} • {s.product} {s.managed ? `• ${s.playbook_mode || 'ON'}` : '• UNMANAGED'}
              </MenuItem>
            ))}
          </Select>
          <Button size="small" variant="outlined" onClick={() => void loadAll(shadowId)} disabled={!shadowId || loading}>
            Refresh
          </Button>
        </Stack>
      </Stack>

      {error ? (
        <Paper variant="outlined" sx={{ mt: 1, p: 1, borderColor: 'error.main' }}>
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        </Paper>
      ) : null}

      <Divider sx={{ my: 1 }} />

      {loading ? (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
          <CircularProgress size={18} />
          <Typography variant="body2">Loading…</Typography>
        </Stack>
      ) : (
        <>
          {selectedShadow ? (
            <Paper variant="outlined" sx={{ p: 1, mb: 1 }}>
              <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap">
                <Typography variant="subtitle2">
                  {selectedShadow.symbol} • {selectedShadow.product} • qty {fmtNum(selectedShadow.qty_current, 0)}
                </Typography>
                <Chip size="small" label={selectedShadow.managed ? `Managed • ${selectedShadow.playbook_mode || 'ON'}` : 'Unmanaged'} color={selectedShadow.managed ? 'success' : 'warning'} />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Avg {fmtNum(selectedShadow.avg_price)} • LTP {fmtNum(selectedShadow.ltp)} • P&amp;L {fmtNum(selectedShadow.pnl_abs)} ({fmtNum(selectedShadow.pnl_pct)}%)
              </Typography>
            </Paper>
          ) : null}

          <Paper variant="outlined" sx={{ p: 1, mb: 1 }}>
            <Typography variant="subtitle2">Forecast</Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}>
              <TextField
                label="Outlook %"
                size="small"
                value={forecastOutlook}
                onChange={(e) => setForecastOutlook(e.target.value)}
                placeholder="e.g., +5"
              />
              <TextField
                label="Horizon (days)"
                size="small"
                value={forecastHorizonDays}
                onChange={(e) => setForecastHorizonDays(e.target.value)}
                placeholder="e.g., 20"
              />
              <TextField
                label="Confidence (0-100)"
                size="small"
                value={forecastConfidence}
                onChange={(e) => setForecastConfidence(e.target.value)}
                placeholder="e.g., 60"
              />
              <Button variant="contained" size="small" onClick={() => void handleSaveForecast()} disabled={savingForecast || !shadowId}>
                {savingForecast ? 'Saving…' : 'Save forecast'}
              </Button>
            </Stack>
            <TextField
              label="Thesis (optional)"
              size="small"
              fullWidth
              multiline
              minRows={2}
              sx={{ mt: 1 }}
              value={forecastThesis}
              onChange={(e) => setForecastThesis(e.target.value)}
              placeholder="What would make this trade work, and what would invalidate it?"
            />
            {forecasts.length ? (
              <Box sx={{ mt: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  Recent forecasts
                </Typography>
                {forecasts.slice(0, 5).map((f) => (
                  <Typography key={f.forecast_id} variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {new Date(f.created_at).toLocaleString()} • outlook {f.outlook_pct ?? '—'}% • horizon {f.horizon_days ?? '—'}d • conf {f.confidence ?? '—'}
                  </Typography>
                ))}
              </Box>
            ) : null}
          </Paper>

          <Paper variant="outlined" sx={{ p: 1, mb: 1 }}>
            <Typography variant="subtitle2">Events</Typography>
            {events.length ? (
              <Box sx={{ mt: 1 }}>
                {events.slice(0, 50).map((e) => (
                  <Paper key={e.event_id} variant="outlined" sx={{ p: 1, mb: 0.75, bgcolor: 'background.default' }}>
                    <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap">
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {e.event_type}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(e.ts).toLocaleString()} • {e.source}
                      </Typography>
                    </Stack>
                    {e.notes ? (
                      <Typography variant="body2" color="text.secondary">
                        {e.notes}
                      </Typography>
                    ) : null}
                  </Paper>
                ))}
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                No events.
              </Typography>
            )}
          </Paper>

          <Paper variant="outlined" sx={{ p: 1 }}>
            <Typography variant="subtitle2">Postmortem</Typography>
            {postmortem ? (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2">
                  Closed at {new Date(postmortem.closed_at).toLocaleString()}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Realized P&amp;L {fmtNum(postmortem.realized_pnl_abs)} ({fmtNum(postmortem.realized_pnl_pct)}%)
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  MFE {fmtNum(postmortem.mfe_abs)} ({fmtNum(postmortem.mfe_pct)}%) • MAE {fmtNum(postmortem.mae_abs)} ({fmtNum(postmortem.mae_pct)}%) • Peak {fmtNum(postmortem.peak_price_while_open)}
                </Typography>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                No postmortem yet (position may still be open).
              </Typography>
            )}
          </Paper>
        </>
      )}
    </Box>
  )
}
