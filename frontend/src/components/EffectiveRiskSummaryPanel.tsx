import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DownloadIcon from '@mui/icons-material/Download'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import FormControl from '@mui/material/FormControl'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import Snackbar from '@mui/material/Snackbar'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState } from 'react'

import {
  fetchCompiledRiskPolicy,
  type CompiledRiskResponse,
  type DrawdownScenario,
  type RiskCategory,
  type RiskProduct,
} from '../services/riskCompiled'

const PRODUCTS: RiskProduct[] = ['CNC', 'MIS']
const CATEGORIES: RiskCategory[] = ['LC', 'MC', 'SC', 'ETF']
const SCENARIOS: DrawdownScenario[] = ['NORMAL', 'CAUTION', 'DEFENSE', 'HARD_STOP']

async function writeToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const el = document.createElement('textarea')
  el.value = text
  el.style.position = 'fixed'
  el.style.left = '-1000px'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

function renderSummaryText(data: CompiledRiskResponse): string {
  const lines: string[] = []
  lines.push('Effective Risk Summary')
  lines.push(`Context: product=${data.context.product}, category=${data.context.category}`)
  if (data.context.scenario) lines.push(`Scenario override: ${data.context.scenario}`)
  if (data.context.symbol) lines.push(`Symbol: ${data.context.symbol}`)
  if (data.context.strategy_id) lines.push(`Strategy ID: ${data.context.strategy_id}`)
  lines.push('')
  lines.push(`Risk engine v2 enabled: ${data.inputs.risk_engine_v2_enabled ? 'YES' : 'NO'}`)
  lines.push(`Risk policy enabled: ${data.inputs.risk_policy_enabled ? 'YES' : 'NO'} (source=${data.inputs.risk_policy_source})`)
  lines.push(`Manual equity (INR): ${fmtNum(data.inputs.manual_equity_inr, 0)}`)
  lines.push(`Drawdown%: ${fmtNum(data.inputs.drawdown_pct, 2)}`)
  lines.push(`Drawdown state: ${data.effective.risk_engine_v2.drawdown_state ?? '—'}`)
  lines.push(`Allow new entries: ${data.effective.allow_new_entries ? 'YES' : 'NO'}`)
  if (data.effective.blocking_reasons?.length) {
    lines.push('')
    lines.push('Blocking reasons:')
    for (const r of data.effective.blocking_reasons) lines.push(`- ${r}`)
  }
  lines.push('')
  lines.push('Overrides:')
  if (!data.overrides?.length) {
    lines.push('- (none)')
  } else {
    for (const o of data.overrides) {
      lines.push(`- ${o.field}: ${String(o.from_value ?? '—')} -> ${String(o.to_value ?? '—')} (${o.source}) ${o.reason}`)
    }
  }
  return lines.join('\n')
}

function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
        {title}
      </Typography>
      <Box sx={{ display: 'grid', gap: 0.5 }}>{children}</Box>
    </Box>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="caption">{value}</Typography>
    </Box>
  )
}

export function EffectiveRiskSummaryPanel() {
  const [product, setProduct] = useState<RiskProduct>('CNC')
  const [category, setCategory] = useState<RiskCategory>('LC')
  const [scenarioMode, setScenarioMode] = useState<'AUTO' | 'MANUAL'>('AUTO')
  const [scenario, setScenario] = useState<DrawdownScenario>('NORMAL')
  const [symbol, setSymbol] = useState('')
  const [strategyId, setStrategyId] = useState('')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<CompiledRiskResponse | null>(null)

  const [snackbar, setSnackbar] = useState<{
    open: boolean
    message: string
    severity: 'success' | 'error' | 'info'
  }>({ open: false, message: '', severity: 'info' })

  const query = useMemo(
    () => ({
      product,
      category,
      scenario: scenarioMode === 'MANUAL' ? scenario : null,
      symbol: symbol.trim() || null,
      strategy_id: strategyId.trim() || null,
    }),
    [product, category, scenarioMode, scenario, symbol, strategyId],
  )

  const load = async () => {
    setBusy(true)
    try {
      const res = await fetchCompiledRiskPolicy({
        product: query.product,
        category: query.category,
        scenario: query.scenario,
        symbol: query.symbol,
        strategy_id: query.strategy_id,
      })
      setData(res)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load compiled risk policy')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const t = window.setTimeout(() => void load(), 150)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  const updatedLabel = useMemo(() => {
    if (!data?.inputs?.compiled_at) return '—'
    try {
      return new Date(data.inputs.compiled_at).toLocaleString()
    } catch {
      return String(data.inputs.compiled_at)
    }
  }, [data?.inputs?.compiled_at])

  return (
    <Paper sx={{ p: 2, position: { xs: 'static', lg: 'sticky' }, top: { lg: 88 } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Effective Risk Summary
        </Typography>
        <Tooltip title="Refresh" arrow placement="top">
          <span>
            <IconButton size="small" onClick={() => void load()} disabled={busy}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        Updated: {updatedLabel} · Policy: {data?.inputs?.risk_policy_source ?? '—'} · Drawdown:{' '}
        {scenarioMode === 'AUTO' ? 'auto' : 'what-if'}
      </Typography>

      <Divider sx={{ my: 1.5 }} />

      <Box sx={{ display: 'grid', gap: 1.25 }}>
        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: '1fr 1fr' }}>
          <FormControl size="small">
            <InputLabel>Product</InputLabel>
            <Select
              value={product}
              label="Product"
              onChange={(e) => setProduct(e.target.value as RiskProduct)}
              inputProps={{ 'aria-label': 'effective-risk-product' }}
            >
              {PRODUCTS.map((p) => (
                <MenuItem key={p} value={p}>
                  {p}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small">
            <InputLabel>Category</InputLabel>
            <Select
              value={category}
              label="Category"
              onChange={(e) => setCategory(e.target.value as RiskCategory)}
              inputProps={{ 'aria-label': 'effective-risk-category' }}
            >
              {CATEGORIES.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: '1fr 1fr' }}>
          <FormControl size="small">
            <InputLabel>Scenario</InputLabel>
            <Select
              value={scenarioMode}
              label="Scenario"
              onChange={(e) => setScenarioMode(e.target.value as 'AUTO' | 'MANUAL')}
              inputProps={{ 'aria-label': 'effective-risk-scenario-mode' }}
            >
              <MenuItem value="AUTO">Auto (live DD%)</MenuItem>
              <MenuItem value="MANUAL">Manual what-if</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" disabled={scenarioMode !== 'MANUAL'}>
            <InputLabel>State</InputLabel>
            <Select
              value={scenario}
              label="State"
              onChange={(e) => setScenario(e.target.value as DrawdownScenario)}
              inputProps={{ 'aria-label': 'effective-risk-scenario-state' }}
            >
              {SCENARIOS.map((s) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        <TextField
          size="small"
          label="Symbol (optional)"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="e.g., NSE:TCS"
        />
        <TextField
          size="small"
          label="Strategy ID (optional)"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
          placeholder="e.g., TrendSwing_v1"
        />
      </Box>

      <Divider sx={{ my: 1.5 }} />

      {error ? (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {error}
        </Alert>
      ) : null}

      {data?.effective?.blocking_reasons?.length ? (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Effective decision: BLOCK NEW ENTRIES
          </Typography>
          <Box component="ul" sx={{ pl: 2.25, my: 0 }}>
            {data.effective.blocking_reasons.map((r) => (
              <li key={r}>
                <Typography variant="caption">{r}</Typography>
              </li>
            ))}
          </Box>
        </Alert>
      ) : null}

      {data ? (
        <>
          <Section title="Gating">
            <Row
              label="Enforcement (Risk policy)"
              value={
                <Chip
                  size="small"
                  label={data.inputs.risk_policy_enabled ? 'ENABLED' : 'DISABLED'}
                  color={data.inputs.risk_policy_enabled ? 'success' : 'default'}
                  variant="outlined"
                />
              }
            />
            <Row
              label="Risk engine v2"
              value={
                <Chip
                  size="small"
                  label={data.inputs.risk_engine_v2_enabled ? 'ENABLED' : 'DISABLED'}
                  color={data.inputs.risk_engine_v2_enabled ? 'success' : 'default'}
                  variant="outlined"
                />
              }
            />
            <Row label="Drawdown%" value={fmtNum(data.inputs.drawdown_pct, 2)} />
            <Row label="Resolved state" value={data.effective.risk_engine_v2.drawdown_state ?? '—'} />
            <Row label="Allow new entries" value={data.effective.allow_new_entries ? 'YES' : 'NO'} />
          </Section>

          <Divider sx={{ my: 1.5 }} />

          <Section title="Account caps (Risk policy)">
            <Row label="Manual equity (INR)" value={fmtNum(data.inputs.manual_equity_inr, 0)} />
            <Row label="Max daily loss %" value={fmtNum(data.effective.risk_policy_by_source.TRADINGVIEW.max_daily_loss_pct, 2)} />
            <Row label="Max daily loss (INR)" value={fmtNum(data.effective.risk_policy_by_source.TRADINGVIEW.max_daily_loss_abs, 0)} />
            <Row label="Max exposure %" value={fmtNum(data.effective.risk_policy_by_source.TRADINGVIEW.max_exposure_pct, 2)} />
            <Row label="Max open positions" value={data.effective.risk_policy_by_source.TRADINGVIEW.max_open_positions} />
            <Row label="Max concurrent symbols" value={data.effective.risk_policy_by_source.TRADINGVIEW.max_concurrent_symbols} />
          </Section>

          <Divider sx={{ my: 1.5 }} />

          <Section title="Sizing (v2 profile + drawdown throttle)">
            <Row label="Throttle multiplier" value={fmtNum(data.effective.risk_engine_v2.throttle_multiplier, 2)} />
            <Row label="Capital per trade (effective)" value={fmtNum(data.effective.risk_engine_v2.capital_per_trade, 0)} />
            <Row label="Max positions (effective)" value={data.effective.risk_engine_v2.max_positions ?? '—'} />
            <Row label="Max exposure % (profile)" value={fmtNum(data.effective.risk_engine_v2.max_exposure_pct, 2)} />
          </Section>

          <Divider sx={{ my: 1.5 }} />

          <Section title="Per-trade risk (Risk policy)">
            <Row label="Max risk per trade %" value={fmtNum(data.effective.risk_policy_by_source.TRADINGVIEW.max_risk_per_trade_pct, 2)} />
            <Row label="Hard risk %" value={fmtNum(data.effective.risk_policy_by_source.TRADINGVIEW.hard_max_risk_pct, 2)} />
            <Row label="Stop mandatory" value={data.effective.risk_policy_by_source.TRADINGVIEW.stop_loss_mandatory ? 'YES' : 'NO'} />
          </Section>

          <Divider sx={{ my: 1.5 }} />

          <Section title="Stops model (Risk policy)">
            <Row label="Stop basis" value={data.effective.risk_policy_by_source.TRADINGVIEW.stop_reference} />
            <Row label="ATR period" value={data.effective.risk_policy_by_source.TRADINGVIEW.atr_period} />
            <Row label="ATR mult (initial stop)" value={fmtNum(data.effective.risk_policy_by_source.TRADINGVIEW.atr_mult_initial_stop, 2)} />
            <Row label="Fallback stop %" value={fmtNum(data.effective.risk_policy_by_source.TRADINGVIEW.fallback_stop_pct, 2)} />
            <Row label="Trailing enabled" value={data.effective.risk_policy_by_source.TRADINGVIEW.trailing_stop_enabled ? 'YES' : 'NO'} />
          </Section>

          <Divider sx={{ my: 1.5 }} />

          <Section title="Trade frequency & loss controls (Risk policy)">
            <Row label="Max trades/symbol/day" value={data.effective.risk_policy_by_source.TRADINGVIEW.max_trades_per_symbol_per_day} />
            <Row label="Min bars between trades" value={data.effective.risk_policy_by_source.TRADINGVIEW.min_bars_between_trades} />
            <Row label="Cooldown after loss (bars)" value={data.effective.risk_policy_by_source.TRADINGVIEW.cooldown_after_loss_bars} />
            <Row label="Max consecutive losses" value={data.effective.risk_policy_by_source.TRADINGVIEW.max_consecutive_losses} />
            <Row label="Pause after streak" value={data.effective.risk_policy_by_source.TRADINGVIEW.pause_after_loss_streak ? 'YES' : 'NO'} />
            <Row label="Pause duration" value={data.effective.risk_policy_by_source.TRADINGVIEW.pause_duration || '—'} />
          </Section>

          {data.context.product === 'MIS' ? (
            <>
              <Divider sx={{ my: 1.5 }} />
              <Section title="MIS-only (v2 profile)">
                <Row label="Entry cutoff time" value={data.effective.risk_engine_v2.entry_cutoff_time ?? '—'} />
                <Row label="Force square-off time" value={data.effective.risk_engine_v2.force_squareoff_time ?? '—'} />
                <Row label="Slippage guard (bps)" value={fmtNum(data.effective.risk_engine_v2.slippage_guard_bps, 1)} />
                <Row label="Gap guard %" value={fmtNum(data.effective.risk_engine_v2.gap_guard_pct, 2)} />
              </Section>
            </>
          ) : null}

          <Divider sx={{ my: 1.5 }} />

          <Section title="Overrides">
            {data.overrides?.length ? (
              <Box component="ul" sx={{ pl: 2.25, my: 0 }}>
                {data.overrides.map((o, idx) => (
                  <li key={`${o.field}-${idx}`}>
                    <Typography variant="caption">
                      {o.field}: {String(o.from_value ?? '—')} → {String(o.to_value ?? '—')} · {o.source}
                    </Typography>
                  </li>
                ))}
              </Box>
            ) : (
              <Typography variant="caption" color="text.secondary">
                No overrides.
              </Typography>
            )}
          </Section>

          <Section title="Provenance (key fields)">
            <Box component="ul" sx={{ pl: 2.25, my: 0 }}>
              {['risk_engine_v2.profile', 'risk_engine_v2.thresholds', 'risk_engine_v2.drawdown_state'].map((k) => (
                <li key={k}>
                  <Typography variant="caption" color="text.secondary">
                    {k}: {data.provenance?.[k]?.source ?? '—'}
                    {data.provenance?.[k]?.detail ? ` (${data.provenance[k]?.detail})` : ''}
                  </Typography>
                </li>
              ))}
            </Box>
          </Section>

          <Divider sx={{ my: 1.5 }} />

          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button
              size="small"
              variant="outlined"
              startIcon={<ContentCopyIcon />}
              onClick={async () => {
                try {
                  await writeToClipboard(renderSummaryText(data))
                  setSnackbar({ open: true, message: 'Copied summary to clipboard.', severity: 'success' })
                } catch (e) {
                  setSnackbar({ open: true, message: e instanceof Error ? e.message : 'Copy failed', severity: 'error' })
                }
              }}
            >
              Copy summary
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={async () => {
                try {
                  await writeToClipboard(JSON.stringify(data, null, 2))
                  setSnackbar({ open: true, message: 'Copied JSON to clipboard.', severity: 'success' })
                } catch (e) {
                  setSnackbar({ open: true, message: e instanceof Error ? e.message : 'Copy failed', severity: 'error' })
                }
              }}
            >
              Export JSON
            </Button>
          </Box>
        </>
      ) : (
        <Typography variant="caption" color="text.secondary">
          {busy ? 'Loading…' : 'No data.'}
        </Typography>
      )}

      <Snackbar
        open={snackbar.open}
        autoHideDuration={2500}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
      >
        <Alert
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Paper>
  )
}
