import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import {
  fetchRiskSettings,
  fetchStrategies,
  createRiskSettings,
  deleteRiskSettings,
  updateStrategyExecutionMode,
  updateStrategyExecutionTarget,
  updateStrategyPaperPollInterval,
  type RiskSettings,
  type Strategy,
} from '../services/admin'

import {
  connectZerodha,
  fetchZerodhaLoginUrl,
  fetchZerodhaStatus,
  type ZerodhaStatus,
} from '../services/zerodha'
import {
  connectAngelone,
  fetchAngeloneStatus,
  type AngeloneStatus,
} from '../services/angelone'
import {
  fetchBrokerSecrets,
  updateBrokerSecret,
  deleteBrokerSecret,
  type BrokerSecret,
} from '../services/brokers'
import { fetchMarketDataStatus, type MarketDataStatus } from '../services/marketData'
import { recordAppLog } from '../services/logs'
import { useTimeSettings } from '../timeSettingsContext'
import { getSystemTimeZone, isValidIanaTimeZone } from '../timeSettings'
import { formatInTimeZone } from '../utils/datetime'

const DISPLAY_TZ_PRESETS = [
  'Asia/Kolkata',
  'LOCAL',
  'UTC',
  'Europe/London',
  'America/New_York',
  'America/Los_Angeles',
] as const

function BrokerSecretsTable({
  brokerName,
}: {
  brokerName: string
}) {
  const [secrets, setSecrets] = useState<BrokerSecret[]>([])
  const [newSecretKey, setNewSecretKey] = useState('')
  const [newSecretValue, setNewSecretValue] = useState('')
  const [secretVisibility, setSecretVisibility] = useState<Record<string, boolean>>({})
  const [isSavingSecret, setIsSavingSecret] = useState(false)
  const [editingSecrets, setEditingSecrets] = useState<Record<string, boolean>>({})
  const [editedKeys, setEditedKeys] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      if (!brokerName) return
      try {
        const res = await fetchBrokerSecrets(brokerName)
        if (!active) return
        setSecrets(res)
        setError(null)
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load broker secrets')
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [brokerName])

  const handleChangeSecretValue = (key: string, value: string) => {
    setSecrets((prev) => prev.map((s) => (s.key === key ? { ...s, value } : s)))
  }

  const handleChangeSecretKey = (originalKey: string, newKey: string) => {
    setEditedKeys((prev) => ({ ...prev, [originalKey]: newKey }))
  }

  const toggleSecretVisibility = (key: string) => {
    setSecretVisibility((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const handleSaveExistingSecret = async (key: string) => {
    const secret = secrets.find((s) => s.key === key)
    if (!brokerName || !secret) return

    const newKey = editedKeys[key]?.trim() || secret.key

    setIsSavingSecret(true)
    try {
      const updated = await updateBrokerSecret(brokerName, newKey, secret.value)

      if (newKey !== secret.key) {
        try {
          await deleteBrokerSecret(brokerName, secret.key)
        } catch {
          // ignore
        }
      }

      setSecrets((prev) => {
        const withoutOld = prev.filter((s) => s.key !== secret.key)
        const mapped = withoutOld.map((s) => (s.key === updated.key ? updated : s))
        return mapped.some((s) => s.key === updated.key) ? mapped : [...mapped, updated]
      })
      setEditingSecrets((prev) => ({ ...prev, [key]: false }))
      setEditedKeys((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
      setError(null)
      recordAppLog('INFO', `Updated broker secret for ${brokerName}/${updated.key}`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to update broker secret'
      setError(msg)
      recordAppLog('ERROR', msg)
    } finally {
      setIsSavingSecret(false)
    }
  }

  const handleAddSecret = async () => {
    const key = newSecretKey.trim()
    const value = newSecretValue
    if (!brokerName || !key) {
      setError('Please provide a key name for the secret.')
      return
    }

    setIsSavingSecret(true)
    try {
      const created = await updateBrokerSecret(brokerName, key, value)
      setSecrets((prev) => {
        const existing = prev.find((s) => s.key === created.key)
        if (existing) return prev.map((s) => (s.key === created.key ? created : s))
        return [...prev, created]
      })
      setNewSecretKey('')
      setNewSecretValue('')
      setEditingSecrets((prev) => ({ ...prev, [created.key]: false }))
      setError(null)
      recordAppLog('INFO', `Saved broker secret for ${brokerName}/${created.key}`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to save broker secret'
      setError(msg)
      recordAppLog('ERROR', msg)
    } finally {
      setIsSavingSecret(false)
    }
  }

  return (
    <>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Key</TableCell>
            <TableCell>Value</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {secrets.map((s) => (
            <TableRow key={s.key}>
              <TableCell sx={{ width: '35%' }}>
                <TextField
                  size="small"
                  value={editingSecrets[s.key] ? editedKeys[s.key] ?? s.key : s.key}
                  fullWidth
                  disabled={!editingSecrets[s.key]}
                  onChange={(e) => handleChangeSecretKey(s.key, e.target.value)}
                />
              </TableCell>
              <TableCell sx={{ width: '45%' }}>
                <TextField
                  size="small"
                  type={secretVisibility[s.key] ? 'text' : 'password'}
                  value={s.value}
                  onChange={(e) => handleChangeSecretValue(s.key, e.target.value)}
                  fullWidth
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          size="small"
                          aria-label="toggle secret visibility"
                          onClick={() => toggleSecretVisibility(s.key)}
                          edge="end"
                        >
                          {secretVisibility[s.key] ? 'Hide' : 'Show'}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />
              </TableCell>
              <TableCell align="right">
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => void handleSaveExistingSecret(s.key)}
                  disabled={isSavingSecret}
                >
                  Save
                </Button>
                <Button
                  size="small"
                  variant="text"
                  sx={{ ml: 1 }}
                  onClick={() =>
                    setEditingSecrets((prev) => ({
                      ...prev,
                      [s.key]: !prev[s.key],
                    }))
                  }
                >
                  {editingSecrets[s.key] ? 'Cancel' : 'Edit'}
                </Button>
                <Button
                  size="small"
                  color="error"
                  variant="text"
                  sx={{ ml: 1 }}
                  onClick={async () => {
                    try {
                      await deleteBrokerSecret(brokerName, s.key)
                      setSecrets((prev) => prev.filter((x) => x.key !== s.key))
                      setEditingSecrets((prev) => {
                        const next = { ...prev }
                        delete next[s.key]
                        return next
                      })
                      setEditedKeys((prev) => {
                        const next = { ...prev }
                        delete next[s.key]
                        return next
                      })
                      setError(null)
                      recordAppLog('INFO', `Deleted broker secret for ${brokerName}/${s.key}`)
                    } catch (err) {
                      const msg =
                        err instanceof Error ? err.message : 'Failed to delete broker secret'
                      setError(msg)
                      recordAppLog('ERROR', msg)
                    }
                  }}
                >
                  Delete
                </Button>
              </TableCell>
            </TableRow>
          ))}
          <TableRow>
            <TableCell>
              <TextField
                size="small"
                placeholder="api_key"
                value={newSecretKey}
                onChange={(e) => setNewSecretKey(e.target.value)}
                fullWidth
              />
            </TableCell>
            <TableCell>
              <TextField
                size="small"
                type={secretVisibility.__new ? 'text' : 'password'}
                value={newSecretValue}
                onChange={(e) => setNewSecretValue(e.target.value)}
                fullWidth
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        size="small"
                        aria-label="toggle secret visibility"
                        onClick={() =>
                          setSecretVisibility((prev) => ({
                            ...prev,
                            __new: !prev.__new,
                          }))
                        }
                        edge="end"
                      >
                        {secretVisibility.__new ? 'Hide' : 'Show'}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
            </TableCell>
            <TableCell align="right">
              <Button
                size="small"
                variant="contained"
                onClick={() => void handleAddSecret()}
                disabled={isSavingSecret}
              >
                Add
              </Button>
            </TableCell>
          </TableRow>
          {secrets.length === 0 && (
            <TableRow>
              <TableCell colSpan={3}>
                <Typography variant="body2" color="text.secondary">
                  No secrets configured yet for this broker.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {error && (
        <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
          {error}
        </Typography>
      )}
    </>
  )
}

export function SettingsPage() {
  const navigate = useNavigate()
  const location = useLocation()

  const { displayTimeZone, setDisplayTimeZone } = useTimeSettings()
  const systemTimeZone = getSystemTimeZone()

  type SettingsTab = 'broker' | 'risk' | 'strategy' | 'time'
  const [activeTab, setActiveTab] = useState<SettingsTab>('broker')

  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [riskSettings, setRiskSettings] = useState<RiskSettings[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [brokerStatus, setBrokerStatus] = useState<ZerodhaStatus | null>(null)
  const [angeloneStatus, setAngeloneStatus] = useState<AngeloneStatus | null>(null)
  const [zerodhaError, setZerodhaError] = useState<string | null>(null)
  const [angeloneError, setAngeloneError] = useState<string | null>(null)
  const [marketStatus, setMarketStatus] = useState<MarketDataStatus | null>(null)
  const [requestToken, setRequestToken] = useState('')
  const [isConnecting, setIsConnecting] = useState(false)
  const [angeloneClientCode, setAngeloneClientCode] = useState('')
  const [angelonePassword, setAngelonePassword] = useState('')
  const [angeloneTotp, setAngeloneTotp] = useState('')
  const [isConnectingAngelone, setIsConnectingAngelone] = useState(false)
  const [angeloneOtpPromptOpen, setAngeloneOtpPromptOpen] = useState(false)
  const [angeloneOtpDraft, setAngeloneOtpDraft] = useState('')
  const [updatingStrategyId, setUpdatingStrategyId] = useState<number | null>(null)
  const [savingRisk, setSavingRisk] = useState(false)
  const [deletingRiskId, setDeletingRiskId] = useState<number | null>(null)
  const [riskScope, setRiskScope] = useState<'GLOBAL' | 'STRATEGY'>('GLOBAL')
  const [riskStrategyId, setRiskStrategyId] = useState<string>('')
  const [riskMaxOrderValue, setRiskMaxOrderValue] = useState<string>('')
  const [riskMaxQty, setRiskMaxQty] = useState<string>('')
  const [riskMaxDailyLoss, setRiskMaxDailyLoss] = useState<string>('')
  const [riskClampMode, setRiskClampMode] = useState<'CLAMP' | 'REJECT'>('CLAMP')
  const [riskShortSelling, setRiskShortSelling] = useState<'ALLOWED' | 'DISABLED'>(
    'ALLOWED',
  )

  const [requestTokenVisible, setRequestTokenVisible] = useState(false)
  const [paperPollDrafts, setPaperPollDrafts] = useState<Record<number, string>>({})
  const displayTzIsPreset = DISPLAY_TZ_PRESETS.includes(displayTimeZone as any)
  const [showCustomTz, setShowCustomTz] = useState<boolean>(
    () => !displayTzIsPreset && displayTimeZone !== 'LOCAL',
  )
  const [customTzDraft, setCustomTzDraft] = useState<string>(() =>
    !displayTzIsPreset && displayTimeZone !== 'LOCAL' ? displayTimeZone : '',
  )

  useEffect(() => {
    const isPreset = DISPLAY_TZ_PRESETS.includes(displayTimeZone as any)
    if (displayTimeZone === 'LOCAL' || isPreset) {
      setShowCustomTz(false)
      setCustomTzDraft('')
      return
    }
    setShowCustomTz(true)
    setCustomTzDraft(displayTimeZone)
  }, [displayTimeZone])

  useEffect(() => {
    const tab = new URLSearchParams(location.search).get('tab')
    if (tab === 'broker' || tab === 'risk' || tab === 'strategy' || tab === 'time') {
      if (tab !== activeTab) setActiveTab(tab)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search])

  const handleTabChange = (_event: React.SyntheticEvent, next: string) => {
    const nextTab: SettingsTab =
      next === 'risk'
        ? 'risk'
        : next === 'strategy'
          ? 'strategy'
          : next === 'time'
            ? 'time'
            : 'broker'
    setActiveTab(nextTab)
    const params = new URLSearchParams(location.search)
    params.set('tab', nextTab)
    navigate(
      { pathname: location.pathname, search: params.toString() },
      { replace: true },
    )
  }

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const [strategiesData, riskData] = await Promise.all([
          fetchStrategies(),
          fetchRiskSettings(),
        ])
        if (!active) return
        setStrategies(strategiesData)
        setRiskSettings(riskData)
        setError(null)
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load settings')
      } finally {
        if (active) setLoading(false)
      }
    }

    void load()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const loadStatus = async () => {
      try {
        const [z, ao, md] = await Promise.allSettled([
          fetchZerodhaStatus(),
          fetchAngeloneStatus(),
          fetchMarketDataStatus(),
        ])
        if (!active) return
        if (z.status === 'fulfilled') {
          setBrokerStatus(z.value)
          setZerodhaError(null)
        } else {
          setBrokerStatus(null)
          setZerodhaError('Failed to load Zerodha status.')
        }
        if (ao.status === 'fulfilled') {
          setAngeloneStatus(ao.value)
          setAngeloneError(null)
        } else {
          setAngeloneStatus(null)
          setAngeloneError('Failed to load AngelOne status.')
        }
        if (md.status === 'fulfilled') setMarketStatus(md.value)
      } catch (err) {
        if (!active) return
        const msg = err instanceof Error ? err.message : 'Failed to load broker status'
        setZerodhaError(msg)
        setAngeloneError(msg)
      }
    }
    void loadStatus()
    return () => {
      active = false
    }
  }, [])

  const handleOpenZerodhaLogin = async () => {
    try {
      const url = await fetchZerodhaLoginUrl()
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Failed to open Zerodha login'
      setZerodhaError(msg)
      recordAppLog('ERROR', msg)
    }
  }

  const handleConnectZerodha = async () => {
    if (!requestToken.trim()) {
      setZerodhaError('Please paste the request_token from Zerodha.')
      return
    }
    setIsConnecting(true)
    try {
      await connectZerodha(requestToken.trim())
      const status = await fetchZerodhaStatus()
      setBrokerStatus(status)
      setZerodhaError(null)
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Failed to complete Zerodha connect'
      setZerodhaError(msg)
      recordAppLog('ERROR', msg)
    } finally {
      setIsConnecting(false)
    }
  }

  const handleConnectAngelone = async () => {
    if (!angeloneClientCode.trim()) {
      setAngeloneError('Please enter AngelOne client code.')
      return
    }
    if (!angelonePassword) {
      setAngeloneError('Please enter AngelOne password.')
      return
    }
    if (!angeloneTotp.trim()) {
      setAngeloneOtpDraft('')
      setAngeloneOtpPromptOpen(true)
      return
    }
    await connectAngeloneWithTotp(angeloneTotp.trim())
  }

  const connectAngeloneWithTotp = async (totp: string) => {
    setIsConnectingAngelone(true)
    try {
      await connectAngelone({
        client_code: angeloneClientCode.trim(),
        password: angelonePassword,
        totp,
      })
      const status = await fetchAngeloneStatus()
      setAngeloneStatus(status)
      setAngeloneError(null)
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Failed to complete AngelOne connect'
      setAngeloneError(msg)
      recordAppLog('ERROR', msg)
    } finally {
      setIsConnectingAngelone(false)
    }
  }

  const handleChangeExecutionMode = async (
    strategy: Strategy,
    newMode: Strategy['execution_mode'],
  ) => {
    if (strategy.execution_mode === newMode) return
    setUpdatingStrategyId(strategy.id)
    try {
      const updated = await updateStrategyExecutionMode(strategy.id, newMode)
      setStrategies((prev) =>
        prev.map((s) => (s.id === updated.id ? updated : s)),
      )
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to update strategy mode',
      )
    } finally {
      setUpdatingStrategyId(null)
    }
  }

  const handleChangeExecutionTarget = async (
    strategy: Strategy,
    newTarget: Strategy['execution_target'],
  ) => {
    if (strategy.execution_target === newTarget) return
    setUpdatingStrategyId(strategy.id)
    try {
      const updated = await updateStrategyExecutionTarget(strategy.id, newTarget)
      setStrategies((prev) =>
        prev.map((s) => (s.id === updated.id ? updated : s)),
      )
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to update strategy execution target',
      )
    } finally {
      setUpdatingStrategyId(null)
    }
  }

  const handleChangePaperPollInterval = async (
    strategy: Strategy,
    value: string,
  ) => {
    const trimmed = value.trim()
    const parsed =
      trimmed === '' ? null : Number.isFinite(Number(trimmed)) ? Number(trimmed) : null
    if (trimmed !== '' && parsed == null) {
      setError('Paper poll interval must be a number of seconds.')
      return
    }
    setUpdatingStrategyId(strategy.id)
    try {
      const updated = await updateStrategyPaperPollInterval(
        strategy.id,
        parsed,
      )
      setStrategies((prev) =>
        prev.map((s) => (s.id === updated.id ? updated : s)),
      )
      setPaperPollDrafts((prev) => {
        const next = { ...prev }
        delete next[strategy.id]
        return next
      })
      setError(null)
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Failed to update paper poll interval'
      if (
        msg.includes('paper_poll_interval_sec') &&
        (msg.includes('number.not_ge') || msg.includes('number.not_le'))
      ) {
        setError('Paper poll interval must be between 15 and 14400 seconds.')
      } else {
        setError(msg)
      }
    } finally {
      setUpdatingStrategyId(null)
    }
  }

  const handleToggleAvailableForAlert = async (
    strategy: Strategy,
    value: boolean,
  ) => {
    if (strategy.available_for_alert === value) return
    setUpdatingStrategyId(strategy.id)
    try {
      const res = await fetch(`/api/strategies/${strategy.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ available_for_alert: value }),
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(
          `Failed to update strategy (${res.status})${
            body ? `: ${body}` : ''
          }`,
        )
      }
      const updated = (await res.json()) as Strategy
      setStrategies((prev) =>
        prev.map((s) => (s.id === updated.id ? updated : s)),
      )
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to update alert availability',
      )
    } finally {
      setUpdatingStrategyId(null)
    }
  }

  const handleSaveRiskSettings = async () => {
    try {
      if (riskScope === 'STRATEGY' && !riskStrategyId) {
        setError('Please select a strategy for STRATEGY scope risk settings.')
        return
      }

      const payload: {
        scope: RiskSettings['scope']
        strategy_id: number | null
        max_order_value?: number
        max_quantity_per_order?: number
        max_daily_loss?: number
        allow_short_selling: boolean
        max_open_positions?: number | null
        clamp_mode: RiskSettings['clamp_mode']
        symbol_whitelist?: string | null
        symbol_blacklist?: string | null
      } = {
        scope: riskScope,
        strategy_id:
          riskScope === 'STRATEGY' ? Number(riskStrategyId) : null,
        allow_short_selling: riskShortSelling === 'ALLOWED',
        clamp_mode: riskClampMode,
      }

      if (riskMaxOrderValue.trim() !== '') {
        const v = Number(riskMaxOrderValue)
        if (!Number.isFinite(v) || v <= 0) {
          setError('Max order value must be a positive number.')
          return
        }
        payload.max_order_value = v
      }

      if (riskMaxQty.trim() !== '') {
        const v = Number(riskMaxQty)
        if (!Number.isFinite(v) || v <= 0) {
          setError('Max quantity per order must be a positive number.')
          return
        }
        payload.max_quantity_per_order = v
      }

      if (riskMaxDailyLoss.trim() !== '') {
        const v = Number(riskMaxDailyLoss)
        if (!Number.isFinite(v) || v <= 0) {
          setError('Max daily loss must be a positive number.')
          return
        }
        payload.max_daily_loss = v
      }

      setSavingRisk(true)
      const created = await createRiskSettings(payload)
      setRiskSettings((prev) => [...prev, created])
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to save risk settings',
      )
    } finally {
      setSavingRisk(false)
    }
  }

  const handleDeleteRiskSettings = async (riskId: number) => {
    const confirmed = window.confirm('Delete this risk row?')
    if (!confirmed) return
    setDeletingRiskId(riskId)
    try {
      await deleteRiskSettings(riskId)
      setRiskSettings((prev) => prev.filter((rs) => rs.id !== riskId))
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to delete risk settings',
      )
    } finally {
      setDeletingRiskId(null)
    }
  }

  return (
    <Box>
      <Dialog
        open={angeloneOtpPromptOpen}
        onClose={() => setAngeloneOtpPromptOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Enter AngelOne OTP/TOTP</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Enter the OTP/TOTP you received/generated, then continue to connect.
          </Typography>
          <TextField
            autoFocus
            size="small"
            label="TOTP/OTP"
            value={angeloneOtpDraft}
            onChange={(e) => setAngeloneOtpDraft(e.target.value)}
            fullWidth
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAngeloneOtpPromptOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!angeloneOtpDraft.trim() || isConnectingAngelone}
            onClick={async () => {
              const totp = angeloneOtpDraft.trim()
              if (!totp) return
              setAngeloneOtpPromptOpen(false)
              setAngeloneTotp(totp)
              await connectAngeloneWithTotp(totp)
            }}
          >
            Continue
          </Button>
        </DialogActions>
      </Dialog>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Manage strategies, risk settings, and broker connection details.
      </Typography>

      <Paper sx={{ mb: 2 }}>
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab value="broker" label="Broker settings" />
          <Tab value="risk" label="Risk settings" />
          <Tab value="strategy" label="Strategy settings" />
          <Tab value="time" label="Time" />
        </Tabs>
      </Paper>

      {activeTab === 'broker' && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mb: 3 }}>
          <Typography variant="h6">Broker Settings</Typography>
          <Typography variant="body2" color="text.secondary">
            Connect brokers and manage API keys/secrets. Brokers are active simultaneously.
          </Typography>

          <Paper sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
              <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 220 }}>
                Zerodha (Kite)
              </Typography>
              <Chip
                size="small"
                label={brokerStatus?.connected ? 'Zerodha: Connected' : 'Zerodha: Not connected'}
                color={brokerStatus?.connected ? 'success' : 'default'}
              />
              {marketStatus && marketStatus.canonical_broker === 'zerodha' && (
                <Chip
                  size="small"
                  label={marketStatus.available ? 'Market data: Available' : 'Market data: Unavailable'}
                  color={marketStatus.available ? 'success' : 'warning'}
                />
              )}
            </Box>

            {brokerStatus?.connected && brokerStatus.user_id && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                Zerodha user:{' '}
                {brokerStatus.user_name
                  ? `${brokerStatus.user_name} (${brokerStatus.user_id})`
                  : brokerStatus.user_id}
              </Typography>
            )}

            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
              Zerodha connection
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Open the Zerodha login page, complete login, then paste the <code>request_token</code>.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
              <Button variant="outlined" size="small" onClick={handleOpenZerodhaLogin}>
                Open Zerodha Login
              </Button>
              <TextField
                size="small"
                label="request_token"
                type={requestTokenVisible ? 'text' : 'password'}
                value={requestToken}
                onChange={(e) => setRequestToken(e.target.value)}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        size="small"
                        aria-label="toggle request token visibility"
                        onClick={() => setRequestTokenVisible((prev) => !prev)}
                        edge="end"
                      >
                        {requestTokenVisible ? 'Hide' : 'Show'}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
              <Button
                variant="contained"
                size="small"
                disabled={isConnecting}
                onClick={handleConnectZerodha}
              >
                {isConnecting ? 'Connecting…' : 'Connect Zerodha'}
              </Button>
            </Box>

            <BrokerSecretsTable brokerName="zerodha" />
            {zerodhaError && (
              <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
                {zerodhaError}
              </Typography>
            )}
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
              <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 220 }}>
                AngelOne (SmartAPI)
              </Typography>
              <Chip
                size="small"
                label={angeloneStatus?.connected ? 'AngelOne: Connected' : 'AngelOne: Not connected'}
                color={angeloneStatus?.connected ? 'success' : 'default'}
              />
              {marketStatus && marketStatus.canonical_broker === 'zerodha' && (
                <Chip
                  size="small"
                  label={marketStatus.available ? 'Market data: Available' : 'Market data: Unavailable'}
                  color={marketStatus.available ? 'success' : 'warning'}
                />
              )}
            </Box>

            {angeloneStatus?.connected && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                AngelOne user:{' '}
                {angeloneStatus.name && angeloneStatus.client_code
                  ? `${angeloneStatus.name} (${angeloneStatus.client_code})`
                  : angeloneStatus.client_code ?? 'Connected'}
              </Typography>
            )}

            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
              AngelOne connection
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              SmartAPI login requires Client Code + Password/MPIN + TOTP/OTP. You’ll need to re-enter OTP/PIN when the session expires.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
              <TextField
                size="small"
                label="client_code"
                value={angeloneClientCode}
                onChange={(e) => setAngeloneClientCode(e.target.value)}
              />
              <TextField
                size="small"
                label="password / MPIN"
                type="password"
                value={angelonePassword}
                onChange={(e) => setAngelonePassword(e.target.value)}
              />
              <TextField
                size="small"
                label="TOTP/OTP"
                value={angeloneTotp}
                onChange={(e) => setAngeloneTotp(e.target.value)}
                placeholder="Leave blank to be prompted"
              />
              <Button
                variant="contained"
                size="small"
                disabled={isConnectingAngelone}
                onClick={handleConnectAngelone}
              >
                {isConnectingAngelone ? 'Connecting…' : 'Connect AngelOne'}
              </Button>
            </Box>

            <BrokerSecretsTable brokerName="angelone" />
            {angeloneError && (
              <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
                {angeloneError}
              </Typography>
            )}
          </Paper>
        </Box>
      )}

      {activeTab === 'time' ? (
        <Paper sx={{ mb: 3, p: 2 }}>
          <Typography variant="h6" gutterBottom>
            Display timezone
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            This only affects how timestamps are displayed in the UI (tables, logs, history). Rebalance scheduling remains fixed to IST.
          </Typography>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
            {(() => {
              const previewTimeZone =
                showCustomTz && customTzDraft.trim()
                  ? customTzDraft.trim()
                  : displayTimeZone === 'LOCAL'
                    ? undefined
                    : displayTimeZone
              const previewValid =
                previewTimeZone == null || isValidIanaTimeZone(previewTimeZone)
              return (
                <>
            <TextField
              select
              label="Timezone"
              value={showCustomTz ? 'CUSTOM' : displayTimeZone}
              onChange={(e) => {
                const v = e.target.value
                if (v === 'CUSTOM') {
                  setShowCustomTz(true)
                  setCustomTzDraft(
                    displayTimeZone === 'LOCAL'
                      ? systemTimeZone ?? ''
                      : String(displayTimeZone),
                  )
                  return
                }
                setShowCustomTz(false)
                setCustomTzDraft('')
                setDisplayTimeZone(v)
              }}
              helperText={
                displayTimeZone === 'LOCAL'
                  ? `Using system timezone${systemTimeZone ? `: ${systemTimeZone}` : ''}.`
                  : `Using ${displayTimeZone}.`
              }
            >
              <MenuItem value="Asia/Kolkata">IST (Asia/Kolkata)</MenuItem>
              <MenuItem value="LOCAL">
                Local (system){systemTimeZone ? ` — ${systemTimeZone}` : ''}
              </MenuItem>
              <MenuItem value="UTC">UTC</MenuItem>
              <MenuItem value="Europe/London">UK (Europe/London)</MenuItem>
              <MenuItem value="America/New_York">US East (America/New_York)</MenuItem>
              <MenuItem value="America/Los_Angeles">US West (America/Los_Angeles)</MenuItem>
              <MenuItem value="CUSTOM">Custom (IANA timezone…)</MenuItem>
            </TextField>

            {showCustomTz ? (
              <TextField
                label="Custom timezone (IANA)"
                value={customTzDraft}
                onChange={(e) => setCustomTzDraft(e.target.value)}
                error={
                  Boolean(customTzDraft.trim()) &&
                  !isValidIanaTimeZone(customTzDraft.trim())
                }
                helperText="Example: Asia/Kolkata, Europe/London, America/New_York"
              />
            ) : null}

            {showCustomTz ? (
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button
                  variant="contained"
                  disabled={
                    !customTzDraft.trim() ||
                    !isValidIanaTimeZone(customTzDraft.trim())
                  }
                  onClick={() => {
                    const tz = customTzDraft.trim()
                    if (!tz || !isValidIanaTimeZone(tz)) return
                    setDisplayTimeZone(tz)
                  }}
                >
                  Apply custom timezone
                </Button>
                <Button
                  variant="text"
                  onClick={() => {
                    setShowCustomTz(false)
                    setCustomTzDraft('')
                  }}
                >
                  Cancel
                </Button>
              </Box>
            ) : null}

            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">Preview</Typography>
              <Typography color="text.secondary" variant="body2">
                Now (display):{' '}
                {previewValid
                  ? formatInTimeZone(new Date().toISOString(), previewTimeZone)
                  : 'Invalid timezone'}
              </Typography>
              <Typography color="text.secondary" variant="body2">
                Now (IST): {formatInTimeZone(new Date().toISOString(), 'Asia/Kolkata')}
              </Typography>
            </Paper>
                </>
              )
            })()}
          </Box>
        </Paper>
      ) : activeTab !== 'broker' && loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">
            {activeTab === 'risk'
              ? 'Loading risk settings...'
              : activeTab === 'strategy'
                ? 'Loading strategy settings...'
                : 'Loading settings...'}
          </Typography>
        </Box>
      ) : activeTab !== 'broker' && error ? (
        <Typography color="error" variant="body2">
          {error}
        </Typography>
      ) : activeTab === 'strategy' ? (
          <Paper sx={{ mb: 3, p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Strategies
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Mode</TableCell>
                  <TableCell>Execution Target</TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                      <Typography variant="body2">
                        Paper Poll Interval (sec)
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        15–14400 sec (leave blank for default)
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell>Enabled</TableCell>
                  <TableCell>Available for alert</TableCell>
                  <TableCell>Description</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {strategies.map((strategy) => (
                  <TableRow key={strategy.id}>
                    <TableCell>{strategy.name}</TableCell>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        value={strategy.execution_mode}
                        onChange={(e) =>
                          handleChangeExecutionMode(
                            strategy,
                            e.target.value as Strategy['execution_mode'],
                          )
                        }
                        disabled={updatingStrategyId === strategy.id}
                      >
                        <MenuItem value="MANUAL">MANUAL</MenuItem>
                        <MenuItem value="AUTO">AUTO</MenuItem>
                      </TextField>
                    </TableCell>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        value={strategy.execution_target}
                        onChange={(e) =>
                          handleChangeExecutionTarget(
                            strategy,
                            e.target.value as Strategy['execution_target'],
                          )
                        }
                        disabled={updatingStrategyId === strategy.id}
                      >
                        <MenuItem value="LIVE">LIVE</MenuItem>
                        <MenuItem value="PAPER">PAPER</MenuItem>
                      </TextField>
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        type="number"
                        placeholder="60"
                        value={
                          paperPollDrafts[strategy.id] ??
                          (strategy.paper_poll_interval_sec != null
                            ? String(strategy.paper_poll_interval_sec)
                            : '')
                        }
                        onChange={(e) =>
                          setPaperPollDrafts((prev) => ({
                            ...prev,
                            [strategy.id]: e.target.value,
                          }))
                        }
                        onBlur={(e) =>
                          void handleChangePaperPollInterval(
                            strategy,
                            e.target.value,
                          )
                        }
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            void handleChangePaperPollInterval(
                              strategy,
                              (e.target as HTMLInputElement).value,
                            )
                          }
                        }}
                      />
                    </TableCell>
                    <TableCell>{strategy.enabled ? 'Yes' : 'No'}</TableCell>
                    <TableCell>
                      <Chip
                        label={strategy.available_for_alert ? 'Yes' : 'No'}
                        size="small"
                        color={strategy.available_for_alert ? 'success' : 'default'}
                        onClick={() =>
                          void handleToggleAvailableForAlert(
                            strategy,
                            !strategy.available_for_alert,
                          )
                        }
                        sx={{ cursor: 'pointer' }}
                      />
                    </TableCell>
                    <TableCell>{strategy.description}</TableCell>
                  </TableRow>
                ))}
                {strategies.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <Typography variant="body2" color="text.secondary">
                        No strategies configured yet.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
      ) : activeTab === 'risk' ? (
          <Paper sx={{ mb: 3, p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Risk Settings
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Define global or per-strategy limits. Leave fields blank to skip a particular
              limit; new rows are added to the table below.
            </Typography>
            <Box
              sx={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 1.5,
                alignItems: 'center',
                mb: 2,
              }}
            >
              <TextField
                select
                label="Scope"
                size="small"
                value={riskScope}
                onChange={(e) =>
                  setRiskScope(e.target.value as 'GLOBAL' | 'STRATEGY')
                }
              >
                <MenuItem value="GLOBAL">GLOBAL</MenuItem>
                <MenuItem value="STRATEGY">STRATEGY</MenuItem>
              </TextField>
              {riskScope === 'STRATEGY' && (
                <TextField
                  select
                  label="Strategy"
                  size="small"
                  sx={{ minWidth: 160 }}
                  value={riskStrategyId}
                  onChange={(e) => setRiskStrategyId(e.target.value)}
                >
                  {strategies.map((s) => (
                    <MenuItem key={s.id} value={s.id}>
                      {s.name}
                    </MenuItem>
                  ))}
                </TextField>
              )}
              <TextField
                label="Max Order Value"
                size="small"
                type="number"
                value={riskMaxOrderValue}
                onChange={(e) => setRiskMaxOrderValue(e.target.value)}
              />
              <TextField
                label="Max Qty/Order"
                size="small"
                type="number"
                value={riskMaxQty}
                onChange={(e) => setRiskMaxQty(e.target.value)}
              />
              <TextField
                label="Max Daily Loss"
                size="small"
                type="number"
                value={riskMaxDailyLoss}
                onChange={(e) => setRiskMaxDailyLoss(e.target.value)}
              />
              <TextField
                select
                label="Clamp Mode"
                size="small"
                value={riskClampMode}
                onChange={(e) =>
                  setRiskClampMode(e.target.value as 'CLAMP' | 'REJECT')
                }
              >
                <MenuItem value="CLAMP">CLAMP</MenuItem>
                <MenuItem value="REJECT">REJECT</MenuItem>
              </TextField>
              <TextField
                select
                label="Short Selling"
                size="small"
                value={riskShortSelling}
                onChange={(e) =>
                  setRiskShortSelling(
                    e.target.value as 'ALLOWED' | 'DISABLED',
                  )
                }
              >
                <MenuItem value="ALLOWED">Allowed</MenuItem>
                <MenuItem value="DISABLED">Disabled</MenuItem>
              </TextField>
              <Button
                size="small"
                variant="contained"
                onClick={handleSaveRiskSettings}
                disabled={savingRisk}
              >
                {savingRisk ? 'Saving…' : 'Add Risk Row'}
              </Button>
            </Box>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Scope</TableCell>
                  <TableCell>Strategy ID</TableCell>
                  <TableCell>Max Order Value</TableCell>
                  <TableCell>Max Qty/Order</TableCell>
                  <TableCell>Max Daily Loss</TableCell>
                  <TableCell>Clamp Mode</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {riskSettings.map((rs) => (
                  <TableRow key={rs.id}>
                    <TableCell>{rs.scope}</TableCell>
                    <TableCell>{rs.strategy_id ?? '-'}</TableCell>
                    <TableCell>{rs.max_order_value ?? '-'}</TableCell>
                    <TableCell>{rs.max_quantity_per_order ?? '-'}</TableCell>
                    <TableCell>{rs.max_daily_loss ?? '-'}</TableCell>
                    <TableCell>{rs.clamp_mode}</TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        color="error"
                        variant="text"
                        onClick={() => void handleDeleteRiskSettings(rs.id)}
                        disabled={deletingRiskId === rs.id}
                      >
                        {deletingRiskId === rs.id ? 'Deleting…' : 'Delete'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {riskSettings.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <Typography variant="body2" color="text.secondary">
                        No risk settings configured yet.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
      ) : null}
    </Box>
  )
}
