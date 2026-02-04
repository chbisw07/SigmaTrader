import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
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
  type RiskSourceBucket,
} from '../services/riskCompiled'

const PRODUCTS: RiskProduct[] = ['CNC', 'MIS']
const CATEGORIES: RiskCategory[] = ['LC', 'MC', 'SC', 'ETF']
const SOURCES: RiskSourceBucket[] = ['TRADINGVIEW', 'SIGMATRADER', 'MANUAL']
const ORDER_TYPES = ['MARKET', 'LIMIT', 'SL', 'SL-M'] as const

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
  lines.push(
    `Context: source=${data.context.source_bucket}, product=${data.context.product}, category=${data.context.category}, order_type=${data.context.order_type ?? '—'}`,
  )
  if (data.context.scenario) lines.push(`Scenario override: ${data.context.scenario}`)
  if (data.context.symbol) lines.push(`Symbol: ${data.context.symbol}`)
  if (data.context.strategy_id) lines.push(`Strategy ID: ${data.context.strategy_id}`)
  lines.push('')
  lines.push(`Risk enabled: ${data.inputs.risk_enabled ? 'YES' : 'NO'}`)
  lines.push(`Manual override enabled: ${data.inputs.manual_override_enabled ? 'YES' : 'NO'}`)
  if (data.inputs.manual_override_enabled) {
    if (data.context.source_bucket === 'MANUAL') {
      lines.push('NOTE: Manual override applies to MANUAL orders and bypasses risk blocks (advisory only).')
    } else {
      lines.push(`NOTE: Manual override does NOT apply to ${data.context.source_bucket} orders.`)
    }
  }
  lines.push(`Baseline equity (INR): ${fmtNum(data.inputs.baseline_equity_inr, 0)}`)
  lines.push(`Drawdown%: ${fmtNum(data.inputs.drawdown_pct, 2)}`)
  lines.push(`Drawdown state: ${data.effective.drawdown_state ?? '—'}`)
  lines.push(`Allow new entries: ${data.effective.allow_new_entries ? 'YES' : 'NO'}`)
  if (data.effective.blocking_reasons?.length) {
    lines.push('')
    lines.push('Blocking reasons:')
    for (const r of data.effective.blocking_reasons) lines.push(`- ${r}`)
  }
  if (data.overrides?.length) {
    lines.push('')
    lines.push('Resolved overrides:')
    for (const o of data.overrides) {
      lines.push(`- ${o.field}: ${String(o.from_value ?? '—')} -> ${String(o.to_value ?? '—')} (${o.source}) ${o.reason}`)
    }
  }
  return lines.join('\n')
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
        {title}
      </Typography>
      <Box sx={{ display: 'grid', gap: 0.5 }}>{children}</Box>
    </Box>
  )
}

export function EffectiveRiskSummaryPanel() {
  const [product, setProduct] = useState<RiskProduct>('CNC')
  const [category, setCategory] = useState<RiskCategory>('LC')
  const [sourceBucket, setSourceBucket] = useState<RiskSourceBucket>('TRADINGVIEW')
  const [orderType, setOrderType] = useState<string>('MARKET')

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
      source_bucket: sourceBucket,
      order_type: orderType || null,
      scenario: scenarioMode === 'MANUAL' ? scenario : null,
      symbol: symbol.trim() || null,
      strategy_id: strategyId.trim() || null,
    }),
    [product, category, sourceBucket, orderType, scenarioMode, scenario, symbol, strategyId],
  )

  const load = async () => {
    setBusy(true)
    try {
      const res = await fetchCompiledRiskPolicy({
        product: query.product,
        category: query.category,
        source_bucket: query.source_bucket,
        order_type: query.order_type,
        scenario: query.scenario,
        symbol: query.symbol,
        strategy_id: query.strategy_id,
      })
      setData(res)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load effective risk summary')
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

  const copySummary = async () => {
    if (!data) return
    try {
      await writeToClipboard(renderSummaryText(data))
      setSnackbar({ open: true, message: 'Copied', severity: 'success' })
    } catch {
      setSnackbar({ open: true, message: 'Copy failed', severity: 'error' })
    }
  }

  return (
    <Paper sx={{ p: 2, position: { xs: 'static', lg: 'sticky' }, top: { lg: 88 } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
          Effective Risk Summary
        </Typography>
        <Tooltip title="Copy summary" arrow placement="top">
          <span>
            <IconButton
              size="small"
              aria-label="copy-effective-risk-summary"
              onClick={() => void copySummary()}
              disabled={!data}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Refresh" arrow placement="top">
          <span>
            <IconButton
              size="small"
              aria-label="refresh-effective-risk-summary"
              onClick={() => void load()}
              disabled={busy}
            >
              <RefreshIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        Updated: {updatedLabel}
      </Typography>

      <Divider sx={{ my: 1.5 }} />

      <Box sx={{ display: 'grid', gap: 1.25 }}>
        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: '1fr 1fr' }}>
          <FormControl size="small">
            <InputLabel>Source</InputLabel>
            <Select
              value={sourceBucket}
              label="Source"
              onChange={(e) => setSourceBucket(e.target.value as RiskSourceBucket)}
              inputProps={{ 'aria-label': 'effective-risk-source' }}
            >
              {SOURCES.map((s) => (
                <MenuItem key={s} value={s}>
                  {s === 'MANUAL' ? 'MANUAL (manual orders)' : s}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small">
            <InputLabel>Order type</InputLabel>
            <Select
              value={orderType}
              label="Order type"
              onChange={(e) => setOrderType(String(e.target.value))}
              inputProps={{ 'aria-label': 'effective-risk-order-type' }}
            >
              {ORDER_TYPES.map((t) => (
                <MenuItem key={t} value={t}>
                  {t}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

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
              <MenuItem value="NORMAL">NORMAL</MenuItem>
              <MenuItem value="CAUTION">CAUTION</MenuItem>
              <MenuItem value="DEFENSE">DEFENSE</MenuItem>
              <MenuItem value="HARD_STOP">HARD_STOP</MenuItem>
            </Select>
          </FormControl>
        </Box>

        <TextField
          size="small"
          label="Symbol (optional)"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          inputProps={{ 'aria-label': 'effective-risk-symbol' }}
        />
        <TextField
          size="small"
          label="Strategy ID (optional)"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
          inputProps={{ 'aria-label': 'effective-risk-strategy' }}
        />
      </Box>

      <Divider sx={{ my: 1.5 }} />

      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}

      {data && (
        <>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
            <Chip
              label={data.inputs.risk_enabled ? 'ENFORCEMENT: ON' : 'ENFORCEMENT: OFF'}
              color={data.inputs.risk_enabled ? 'success' : 'default'}
              size="small"
            />
            {data.inputs.manual_override_enabled && data.context.source_bucket === 'MANUAL' ? (
              <Chip
                label="MANUAL OVERRIDE: ON (bypass)"
                color="warning"
                size="small"
                variant="filled"
              />
            ) : null}
            <Chip
              label={data.effective.allow_new_entries ? 'ALLOW: YES' : 'ALLOW: NO'}
              color={data.effective.allow_new_entries ? 'success' : 'error'}
              size="small"
            />
            <Chip
              label={`DD: ${data.effective.drawdown_state ?? '—'}`}
              size="small"
              variant="outlined"
            />
          </Box>

          {data.inputs.manual_override_enabled ? (
            data.context.source_bucket === 'MANUAL' ? (
              <Alert severity="warning" sx={{ mb: 1 }}>
                Manual override is ON. For MANUAL orders, SigmaTrader will warn but will not block on risk
                thresholds. Values shown below are advisory only (structural validity checks still apply).
              </Alert>
            ) : (
              <Alert severity="info" sx={{ mb: 1 }}>
                Manual override is ON, but it applies only to MANUAL orders. {data.context.source_bucket} orders are still fully enforced.
              </Alert>
            )
          ) : null}

          <Section title="Resolved (core)">
            <Row label="Baseline equity (INR)" value={fmtNum(data.inputs.baseline_equity_inr, 0)} />
            <Row label="Drawdown %" value={fmtNum(data.inputs.drawdown_pct, 2)} />
            <Row label="Capital per trade" value={fmtNum(data.effective.capital_per_trade, 0)} />
            <Row label="Max positions" value={data.effective.max_positions ?? '—'} />
            <Row label="Max exposure %" value={fmtNum(data.effective.max_exposure_pct, 2)} />
            <Row label="Daily loss %" value={fmtNum(data.effective.daily_loss_pct, 2)} />
            <Row label="Hard daily loss %" value={fmtNum(data.effective.hard_daily_loss_pct, 2)} />
            <Row label="Max consecutive losses" value={data.effective.max_consecutive_losses ?? '—'} />
          </Section>

          <Section title="Execution Safety (per order)">
            <Row label="Allow product" value={data.effective.allow_product ? 'YES' : 'NO'} />
            <Row label="Allow short selling" value={data.effective.allow_short_selling ? 'YES' : 'NO'} />
            <Row label="Max order value %" value={fmtNum(data.effective.max_order_value_pct, 2)} />
            <Row label="Max order value (abs)" value={fmtNum(data.effective.max_order_value_abs, 0)} />
            <Row label="Max qty/order" value={fmtNum(data.effective.max_quantity_per_order, 0)} />
            <Row label="Order type policy" value={data.effective.order_type_policy || '—'} />
            <Row label="Slippage guard (bps)" value={fmtNum(data.effective.slippage_guard_bps, 1)} />
            <Row label="Gap guard (%)" value={fmtNum(data.effective.gap_guard_pct, 2)} />
          </Section>

          <Section title="Per-Trade Risk (stop-distance)">
            <Row label="Risk per trade %" value={fmtNum(data.effective.risk_per_trade_pct, 3)} />
            <Row label="Hard risk %" value={fmtNum(data.effective.hard_risk_pct, 3)} />
            <Row label="Stop mandatory" value={data.effective.stop_loss_mandatory ? 'YES' : 'NO'} />
            <Row label="Stop reference" value={data.effective.stop_reference || '—'} />
            <Row label="ATR period" value={data.effective.atr_period ?? '—'} />
            <Row label="ATR mult (initial stop)" value={fmtNum(data.effective.atr_mult_initial_stop, 2)} />
            <Row label="Fallback stop %" value={fmtNum(data.effective.fallback_stop_pct, 2)} />
            <Row label="Min stop dist %" value={fmtNum(data.effective.min_stop_distance_pct, 2)} />
            <Row label="Max stop dist %" value={fmtNum(data.effective.max_stop_distance_pct, 2)} />
          </Section>

          <Section title="Time + Frequency">
            <Row label="Entry cutoff" value={data.effective.entry_cutoff_time || '—'} />
            <Row label="Force squareoff" value={data.effective.force_squareoff_time || '—'} />
            <Row label="Max trades/day" value={data.effective.max_trades_per_day ?? '—'} />
            <Row label="Max trades/symbol/day" value={data.effective.max_trades_per_symbol_per_day ?? '—'} />
            <Row label="Min bars between" value={data.effective.min_bars_between_trades ?? '—'} />
            <Row label="Cooldown after loss (bars)" value={data.effective.cooldown_after_loss_bars ?? '—'} />
          </Section>

          {data.effective.blocking_reasons?.length ? (
            <Alert severity="warning" sx={{ mt: 1 }}>
              {data.effective.blocking_reasons.join(' • ')}
            </Alert>
          ) : null}
        </>
      )}

      <Snackbar
        open={snackbar.open}
        autoHideDuration={1200}
        onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        message={snackbar.message}
      />
    </Paper>
  )
}
