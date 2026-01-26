import AddIcon from '@mui/icons-material/Add'
import RefreshIcon from '@mui/icons-material/Refresh'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Switch from '@mui/material/Switch'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState } from 'react'

import {
  createRiskProfile,
  deleteRiskProfile,
  fetchAlertDecisionLog,
  fetchDrawdownThresholds,
  fetchRiskProfiles,
  upsertDrawdownThresholds,
  updateRiskProfile,
  type AlertDecisionLogRow,
  type DrawdownThresholdUpsert,
  type RiskCategory,
  type RiskProduct,
  type RiskProfile,
  type RiskProfileCreate,
} from '../services/riskEngine'

const PRODUCTS: RiskProduct[] = ['CNC', 'MIS']
const CATEGORIES: RiskCategory[] = ['LC', 'MC', 'SC', 'ETF']

function numberOrZero(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function normalizeTimeInput(v: string): string {
  return v.trim()
}

const DEFAULT_PROFILE: RiskProfileCreate = {
  name: '',
  product: 'CNC',
  capital_per_trade: 30000,
  max_positions: 10,
  max_exposure_pct: 30,
  risk_per_trade_pct: 0.075,
  hard_risk_pct: 0.1,
  daily_loss_pct: 0.75,
  hard_daily_loss_pct: 1.0,
  max_consecutive_losses: 3,
  drawdown_mode: 'SETTINGS_BY_CATEGORY',
  force_exit_time: null,
  entry_cutoff_time: null,
  force_squareoff_time: null,
  max_trades_per_day: null,
  max_trades_per_symbol_per_day: null,
  min_bars_between_trades: null,
  cooldown_after_loss_bars: null,
  slippage_guard_bps: null,
  gap_guard_pct: null,
  order_type_policy: null,
  leverage_mode: null,
  max_effective_leverage: null,
  max_margin_used_pct: null,
  enabled: true,
  is_default: false,
}

export function RiskEngineV2Settings() {
  const [profiles, setProfiles] = useState<RiskProfile[]>([])
  const [profilesBusy, setProfilesBusy] = useState(false)
  const [profilesError, setProfilesError] = useState<string | null>(null)

  const [thresholdDrafts, setThresholdDrafts] = useState<
    Record<string, { caution_pct: number; defense_pct: number; hard_stop_pct: number }>
  >({})
  const [thresholdsBusy, setThresholdsBusy] = useState(false)
  const [thresholdsError, setThresholdsError] = useState<string | null>(null)

  const [decisionRows, setDecisionRows] = useState<AlertDecisionLogRow[]>([])
  const [decisionBusy, setDecisionBusy] = useState(false)
  const [decisionError, setDecisionError] = useState<string | null>(null)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState<RiskProfileCreate>({ ...DEFAULT_PROFILE })
  const [saving, setSaving] = useState(false)

  const loadProfiles = async () => {
    setProfilesBusy(true)
    try {
      const res = await fetchRiskProfiles()
      setProfiles(res)
      setProfilesError(null)
    } catch (err) {
      setProfilesError(err instanceof Error ? err.message : 'Failed to load risk profiles')
    } finally {
      setProfilesBusy(false)
    }
  }

  const loadThresholds = async () => {
    setThresholdsBusy(true)
    try {
      const rows = await fetchDrawdownThresholds()
      const next: Record<
        string,
        { caution_pct: number; defense_pct: number; hard_stop_pct: number }
      > = {}
      for (const p of PRODUCTS) {
        for (const c of CATEGORIES) {
          const row = rows.find((r) => r.product === p && r.category === c)
          next[`${p}:${c}`] = {
            caution_pct: numberOrZero(row?.caution_pct ?? 0),
            defense_pct: numberOrZero(row?.defense_pct ?? 0),
            hard_stop_pct: numberOrZero(row?.hard_stop_pct ?? 0),
          }
        }
      }
      setThresholdDrafts(next)
      setThresholdsError(null)
    } catch (err) {
      setThresholdsError(err instanceof Error ? err.message : 'Failed to load thresholds')
    } finally {
      setThresholdsBusy(false)
    }
  }

  const loadDecisionLog = async () => {
    setDecisionBusy(true)
    try {
      const rows = await fetchAlertDecisionLog(200)
      setDecisionRows(rows)
      setDecisionError(null)
    } catch (err) {
      setDecisionError(err instanceof Error ? err.message : 'Failed to load decision log')
    } finally {
      setDecisionBusy(false)
    }
  }

  const defaultBadges = useMemo(() => {
    const out = new Map<number, string>()
    for (const p of profiles) {
      if (p.is_default) out.set(p.id, `Default ${p.product}`)
    }
    return out
  }, [profiles])

  useEffect(() => {
    void loadProfiles()
    void loadThresholds()
    void loadDecisionLog()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreate = () => {
    setEditingId(null)
    setDraft({ ...DEFAULT_PROFILE })
    setEditorOpen(true)
  }

  const openEdit = (p: RiskProfile) => {
    setEditingId(p.id)
    setDraft({
      name: p.name,
      product: p.product,
      capital_per_trade: numberOrZero(p.capital_per_trade),
      max_positions: Math.trunc(numberOrZero(p.max_positions)),
      max_exposure_pct: numberOrZero(p.max_exposure_pct),
      risk_per_trade_pct: numberOrZero(p.risk_per_trade_pct),
      hard_risk_pct: numberOrZero(p.hard_risk_pct),
      daily_loss_pct: numberOrZero(p.daily_loss_pct),
      hard_daily_loss_pct: numberOrZero(p.hard_daily_loss_pct),
      max_consecutive_losses: Math.trunc(numberOrZero(p.max_consecutive_losses)),
      drawdown_mode: 'SETTINGS_BY_CATEGORY',
      force_exit_time: p.force_exit_time ?? null,
      entry_cutoff_time: p.entry_cutoff_time ?? null,
      force_squareoff_time: p.force_squareoff_time ?? null,
      max_trades_per_day: p.max_trades_per_day ?? null,
      max_trades_per_symbol_per_day: p.max_trades_per_symbol_per_day ?? null,
      min_bars_between_trades: p.min_bars_between_trades ?? null,
      cooldown_after_loss_bars: p.cooldown_after_loss_bars ?? null,
      slippage_guard_bps: p.slippage_guard_bps ?? null,
      gap_guard_pct: p.gap_guard_pct ?? null,
      order_type_policy: p.order_type_policy ?? null,
      leverage_mode: p.leverage_mode ?? null,
      max_effective_leverage: p.max_effective_leverage ?? null,
      max_margin_used_pct: p.max_margin_used_pct ?? null,
      enabled: Boolean(p.enabled),
      is_default: Boolean(p.is_default),
    })
    setEditorOpen(true)
  }

  const handleSaveProfile = async () => {
    const name = draft.name.trim()
    if (!name) return
    setSaving(true)
    try {
      const payload: RiskProfileCreate = {
        ...draft,
        name,
        force_exit_time: draft.force_exit_time
          ? normalizeTimeInput(draft.force_exit_time)
          : null,
        entry_cutoff_time: draft.entry_cutoff_time
          ? normalizeTimeInput(draft.entry_cutoff_time)
          : null,
        force_squareoff_time: draft.force_squareoff_time
          ? normalizeTimeInput(draft.force_squareoff_time)
          : null,
        capital_per_trade: numberOrZero(draft.capital_per_trade),
        max_positions: Math.max(0, Math.trunc(numberOrZero(draft.max_positions))),
        max_exposure_pct: numberOrZero(draft.max_exposure_pct),
        risk_per_trade_pct: numberOrZero(draft.risk_per_trade_pct),
        hard_risk_pct: numberOrZero(draft.hard_risk_pct),
        daily_loss_pct: numberOrZero(draft.daily_loss_pct),
        hard_daily_loss_pct: numberOrZero(draft.hard_daily_loss_pct),
        max_consecutive_losses: Math.max(
          0,
          Math.trunc(numberOrZero(draft.max_consecutive_losses)),
        ),
        max_trades_per_day:
          draft.max_trades_per_day == null
            ? null
            : Math.max(0, Math.trunc(numberOrZero(draft.max_trades_per_day))),
        max_trades_per_symbol_per_day:
          draft.max_trades_per_symbol_per_day == null
            ? null
            : Math.max(0, Math.trunc(numberOrZero(draft.max_trades_per_symbol_per_day))),
        min_bars_between_trades:
          draft.min_bars_between_trades == null
            ? null
            : Math.max(0, Math.trunc(numberOrZero(draft.min_bars_between_trades))),
        cooldown_after_loss_bars:
          draft.cooldown_after_loss_bars == null
            ? null
            : Math.max(0, Math.trunc(numberOrZero(draft.cooldown_after_loss_bars))),
        slippage_guard_bps:
          draft.slippage_guard_bps == null ? null : numberOrZero(draft.slippage_guard_bps),
        gap_guard_pct:
          draft.gap_guard_pct == null ? null : numberOrZero(draft.gap_guard_pct),
        order_type_policy: draft.order_type_policy?.trim()
          ? draft.order_type_policy.trim()
          : null,
        leverage_mode: draft.leverage_mode?.trim() ? draft.leverage_mode.trim() : null,
        max_effective_leverage:
          draft.max_effective_leverage == null ? null : numberOrZero(draft.max_effective_leverage),
        max_margin_used_pct:
          draft.max_margin_used_pct == null ? null : numberOrZero(draft.max_margin_used_pct),
      }
      if (editingId == null) {
        await createRiskProfile(payload)
      } else {
        await updateRiskProfile(editingId, payload)
      }
      setEditorOpen(false)
      await loadProfiles()
    } catch (err) {
      setProfilesError(err instanceof Error ? err.message : 'Failed to save risk profile')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteProfile = async (p: RiskProfile) => {
    const ok = window.confirm(`Delete risk profile "${p.name}"?`)
    if (!ok) return
    setProfilesBusy(true)
    try {
      await deleteRiskProfile(p.id)
      await loadProfiles()
    } catch (err) {
      setProfilesError(err instanceof Error ? err.message : 'Failed to delete risk profile')
    } finally {
      setProfilesBusy(false)
    }
  }

  const handleSaveThresholds = async () => {
    setThresholdsBusy(true)
    try {
      const payload: DrawdownThresholdUpsert[] = []
      for (const p of PRODUCTS) {
        for (const c of CATEGORIES) {
          const key = `${p}:${c}`
          const row =
            thresholdDrafts[key] ?? { caution_pct: 0, defense_pct: 0, hard_stop_pct: 0 }
          payload.push({
            product: p,
            category: c,
            caution_pct: numberOrZero(row.caution_pct),
            defense_pct: numberOrZero(row.defense_pct),
            hard_stop_pct: numberOrZero(row.hard_stop_pct),
          })
        }
      }
      await upsertDrawdownThresholds(payload)
      setThresholdsError(null)
    } catch (err) {
      setThresholdsError(err instanceof Error ? err.message : 'Failed to save thresholds')
    } finally {
      setThresholdsBusy(false)
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="h6" sx={{ flex: 1, minWidth: 260 }}>
            Product-specific risk profiles (CNC/MIS)
          </Typography>
          <Tooltip title="Refresh" arrow placement="top">
            <IconButton size="small" onClick={() => void loadProfiles()} disabled={profilesBusy}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Button
            size="small"
            variant="contained"
            startIcon={<AddIcon />}
            onClick={openCreate}
            disabled={profilesBusy}
          >
            Create profile
          </Button>
        </Box>
        <Divider sx={{ my: 2 }} />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Product</TableCell>
              <TableCell>Enabled</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {profiles.map((p) => (
              <TableRow key={p.id}>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                    <span>{p.name}</span>
                    {defaultBadges.has(p.id) ? (
                      <Chip size="small" color="primary" label={defaultBadges.get(p.id)} />
                    ) : null}
                  </Box>
                </TableCell>
                <TableCell>{p.product}</TableCell>
                <TableCell>{p.enabled ? 'Yes' : 'No'}</TableCell>
                <TableCell align="right">
                  <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                    <Button size="small" variant="outlined" onClick={() => openEdit(p)}>
                      Edit
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      onClick={() => void handleDeleteProfile(p)}
                    >
                      Delete
                    </Button>
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {profilesError ? (
          <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
            {profilesError}
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="h6" sx={{ flex: 1, minWidth: 260 }}>
            Drawdown thresholds (by product × category)
          </Typography>
          <Tooltip title="Refresh" arrow placement="top">
            <IconButton size="small" onClick={() => void loadThresholds()} disabled={thresholdsBusy}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Button
            size="small"
            variant="contained"
            onClick={() => void handleSaveThresholds()}
            disabled={thresholdsBusy}
          >
            Save
          </Button>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Uses portfolio-level drawdown % with category-specific thresholds.
        </Typography>
        <Divider sx={{ my: 2 }} />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Product</TableCell>
              <TableCell>Category</TableCell>
              <TableCell>CAUTION %</TableCell>
              <TableCell>DEFENSE %</TableCell>
              <TableCell>HARD STOP %</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {PRODUCTS.flatMap((p) =>
              CATEGORIES.map((c) => {
                const key = `${p}:${c}`
                const row =
                  thresholdDrafts[key] ?? { caution_pct: 0, defense_pct: 0, hard_stop_pct: 0 }
                return (
                  <TableRow key={key}>
                    <TableCell>{p}</TableCell>
                    <TableCell>{c}</TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        type="number"
                        value={row.caution_pct}
                        onChange={(e) =>
                          setThresholdDrafts((prev) => ({
                            ...prev,
                            [key]: { ...row, caution_pct: numberOrZero(e.target.value) },
                          }))
                        }
                        inputProps={{ min: 0, step: '0.1' }}
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        type="number"
                        value={row.defense_pct}
                        onChange={(e) =>
                          setThresholdDrafts((prev) => ({
                            ...prev,
                            [key]: { ...row, defense_pct: numberOrZero(e.target.value) },
                          }))
                        }
                        inputProps={{ min: 0, step: '0.1' }}
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        type="number"
                        value={row.hard_stop_pct}
                        onChange={(e) =>
                          setThresholdDrafts((prev) => ({
                            ...prev,
                            [key]: { ...row, hard_stop_pct: numberOrZero(e.target.value) },
                          }))
                        }
                        inputProps={{ min: 0, step: '0.1' }}
                      />
                    </TableCell>
                  </TableRow>
                )
              }),
            )}
          </TableBody>
        </Table>
        {thresholdsError ? (
          <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
            {thresholdsError}
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="h6" sx={{ flex: 1, minWidth: 260 }}>
            Alert decision log
          </Typography>
          <Tooltip title="Refresh" arrow placement="top">
            <IconButton size="small" onClick={() => void loadDecisionLog()} disabled={decisionBusy}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Shows resolved product/profile/category and whether the order was placed or blocked.
        </Typography>
        <Divider sx={{ my: 2 }} />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Symbol</TableCell>
              <TableCell>Strategy</TableCell>
              <TableCell>Hint</TableCell>
              <TableCell>Resolved</TableCell>
              <TableCell>Category</TableCell>
              <TableCell>DD%</TableCell>
              <TableCell>State</TableCell>
              <TableCell>Decision</TableCell>
              <TableCell>Reasons</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {decisionRows.map((r) => (
              <TableRow key={r.id}>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {new Date(r.created_at).toLocaleString()}
                </TableCell>
                <TableCell>{r.symbol ?? '—'}</TableCell>
                <TableCell>{r.strategy_ref ?? '—'}</TableCell>
                <TableCell>{r.product_hint ?? '—'}</TableCell>
                <TableCell>{r.resolved_product ?? '—'}</TableCell>
                <TableCell>{r.risk_category ?? '—'}</TableCell>
                <TableCell>
                  {r.drawdown_pct != null ? Number(r.drawdown_pct).toFixed(2) : '—'}
                </TableCell>
                <TableCell>{r.drawdown_state ?? '—'}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={r.decision}
                    color={
                      r.decision === 'PLACED'
                        ? 'success'
                        : r.decision === 'BLOCKED'
                          ? 'error'
                          : 'default'
                    }
                    variant={r.decision === 'PLACED' ? 'filled' : 'outlined'}
                  />
                </TableCell>
                <TableCell sx={{ maxWidth: 320 }}>
                  <Typography variant="caption" color="text.secondary">
                    {r.reasons_json}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
            {decisionRows.length === 0 && (
              <TableRow>
                <TableCell colSpan={10}>
                  <Typography variant="caption" color="text.secondary">
                    No decision logs yet.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {decisionError ? (
          <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
            {decisionError}
          </Typography>
        ) : null}
      </Paper>

      <Dialog open={editorOpen} onClose={() => setEditorOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{editingId == null ? 'Create Risk Profile' : 'Edit Risk Profile'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mt: 1 }}>
            <TextField
              size="small"
              label="Name"
              value={draft.name}
              onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
              sx={{ minWidth: 260, flex: 1 }}
            />
            <TextField
              size="small"
              select
              label="Product"
              value={draft.product}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, product: e.target.value as RiskProduct }))
              }
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="CNC">CNC</MenuItem>
              <MenuItem value="MIS">MIS</MenuItem>
            </TextField>
            <FormControlLabel
              control={
                <Switch
                  checked={draft.enabled}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, enabled: e.target.checked }))
                  }
                />
              }
              label="Enabled"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={draft.is_default}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, is_default: e.target.checked }))
                  }
                />
              }
              label="Default"
            />
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Position sizing
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              size="small"
              type="number"
              label="Capital / trade"
              value={draft.capital_per_trade}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  capital_per_trade: numberOrZero(e.target.value),
                }))
              }
              sx={{ minWidth: 180 }}
            />
            <TextField
              size="small"
              type="number"
              label="Max positions"
              value={draft.max_positions}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  max_positions: Math.trunc(numberOrZero(e.target.value)),
                }))
              }
              sx={{ minWidth: 180 }}
            />
            <TextField
              size="small"
              type="number"
              label="Max exposure %"
              value={draft.max_exposure_pct}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  max_exposure_pct: numberOrZero(e.target.value),
                }))
              }
              sx={{ minWidth: 180 }}
            />
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Per-trade risk
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              size="small"
              type="number"
              label="Risk % (of equity)"
              value={draft.risk_per_trade_pct}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  risk_per_trade_pct: numberOrZero(e.target.value),
                }))
              }
              sx={{ minWidth: 220 }}
            />
            <TextField
              size="small"
              type="number"
              label="Hard risk %"
              value={draft.hard_risk_pct}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  hard_risk_pct: numberOrZero(e.target.value),
                }))
              }
              sx={{ minWidth: 200 }}
            />
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Daily limits
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              size="small"
              type="number"
              label="Daily loss %"
              value={draft.daily_loss_pct}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  daily_loss_pct: numberOrZero(e.target.value),
                }))
              }
              sx={{ minWidth: 180 }}
            />
            <TextField
              size="small"
              type="number"
              label="Hard daily loss %"
              value={draft.hard_daily_loss_pct}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  hard_daily_loss_pct: numberOrZero(e.target.value),
                }))
              }
              sx={{ minWidth: 200 }}
            />
            <TextField
              size="small"
              type="number"
              label="Max loss streak"
              value={draft.max_consecutive_losses}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  max_consecutive_losses: Math.trunc(numberOrZero(e.target.value)),
                }))
              }
              sx={{ minWidth: 180 }}
            />
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Time controls (IST)
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              size="small"
              label="Force exit time (HH:MM)"
              value={draft.force_exit_time ?? ''}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, force_exit_time: e.target.value }))
              }
              sx={{ minWidth: 240 }}
            />
            {draft.product === 'MIS' ? (
              <>
                <TextField
                  size="small"
                  label="Entry cutoff time (HH:MM)"
                  value={draft.entry_cutoff_time ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, entry_cutoff_time: e.target.value }))
                  }
                  sx={{ minWidth: 240 }}
                />
                <TextField
                  size="small"
                  label="Force square-off time (HH:MM)"
                  value={draft.force_squareoff_time ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      force_squareoff_time: e.target.value,
                    }))
                  }
                  sx={{ minWidth: 260 }}
                />
              </>
            ) : null}
          </Box>

          {draft.product === 'MIS' ? (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                MIS extensions
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <TextField
                  size="small"
                  type="number"
                  label="Max trades/day"
                  value={draft.max_trades_per_day ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      max_trades_per_day:
                        e.target.value === ''
                          ? null
                          : Math.trunc(numberOrZero(e.target.value)),
                    }))
                  }
                  sx={{ minWidth: 180 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Max trades/symbol/day"
                  value={draft.max_trades_per_symbol_per_day ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      max_trades_per_symbol_per_day:
                        e.target.value === ''
                          ? null
                          : Math.trunc(numberOrZero(e.target.value)),
                    }))
                  }
                  sx={{ minWidth: 220 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Min bars between trades"
                  value={draft.min_bars_between_trades ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      min_bars_between_trades:
                        e.target.value === ''
                          ? null
                          : Math.trunc(numberOrZero(e.target.value)),
                    }))
                  }
                  sx={{ minWidth: 240 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Cooldown after loss (bars)"
                  value={draft.cooldown_after_loss_bars ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      cooldown_after_loss_bars:
                        e.target.value === ''
                          ? null
                          : Math.trunc(numberOrZero(e.target.value)),
                    }))
                  }
                  sx={{ minWidth: 260 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Slippage guard (bps)"
                  value={draft.slippage_guard_bps ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      slippage_guard_bps:
                        e.target.value === '' ? null : numberOrZero(e.target.value),
                    }))
                  }
                  sx={{ minWidth: 220 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Gap guard (%)"
                  value={draft.gap_guard_pct ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      gap_guard_pct:
                        e.target.value === '' ? null : numberOrZero(e.target.value),
                    }))
                  }
                  sx={{ minWidth: 180 }}
                />
                <TextField
                  size="small"
                  label="Order type policy"
                  value={draft.order_type_policy ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, order_type_policy: e.target.value }))
                  }
                  sx={{ minWidth: 220 }}
                />
                <TextField
                  size="small"
                  select
                  label="Leverage mode"
                  value={draft.leverage_mode ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      leverage_mode: e.target.value ? String(e.target.value) : null,
                    }))
                  }
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="">—</MenuItem>
                  <MenuItem value="AUTO">AUTO</MenuItem>
                  <MenuItem value="STATIC">STATIC</MenuItem>
                  <MenuItem value="OFF">OFF</MenuItem>
                </TextField>
                <TextField
                  size="small"
                  type="number"
                  label="Max effective leverage"
                  value={draft.max_effective_leverage ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      max_effective_leverage:
                        e.target.value === '' ? null : numberOrZero(e.target.value),
                    }))
                  }
                  sx={{ minWidth: 220 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Max margin used (%)"
                  value={draft.max_margin_used_pct ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      max_margin_used_pct:
                        e.target.value === '' ? null : numberOrZero(e.target.value),
                    }))
                  }
                  sx={{ minWidth: 200 }}
                />
              </Box>
            </>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditorOpen(false)} disabled={saving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleSaveProfile()}
            disabled={saving || !draft.name.trim()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
