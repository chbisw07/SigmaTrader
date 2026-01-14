import FileDownloadIcon from '@mui/icons-material/FileDownload'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
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
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import {
  fetchRiskSettings,
  createRiskSettings,
  deleteRiskSettings,
  type RiskSettings,
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
import {
  downloadMarketCalendarCsv,
  fetchMarketDefaults,
  listMarketCalendarRows,
  resolveMarketSession,
  uploadMarketCalendarCsv,
  type MarketCalendarRow,
  type MarketDefaults,
  type ResolvedMarketSession,
} from '../services/marketCalendar'
import {
  fetchTradingViewWebhookSecret,
  fetchTradingViewWebhookConfig,
  updateTradingViewWebhookSecret,
  updateTradingViewWebhookConfig,
} from '../services/webhookSettings'
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

  type SettingsTab = 'broker' | 'risk' | 'webhook' | 'market' | 'time'
  const [activeTab, setActiveTab] = useState<SettingsTab>('broker')

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
  const [savingRisk, setSavingRisk] = useState(false)
  const [deletingRiskId, setDeletingRiskId] = useState<number | null>(null)
  const riskScope: 'GLOBAL' = 'GLOBAL'
  const [riskMaxOrderValue, setRiskMaxOrderValue] = useState<string>('')
  const [riskMaxQty, setRiskMaxQty] = useState<string>('')
  const [riskMaxDailyLoss, setRiskMaxDailyLoss] = useState<string>('')
  const [riskClampMode, setRiskClampMode] = useState<'CLAMP' | 'REJECT'>('CLAMP')
  const [riskShortSelling, setRiskShortSelling] = useState<'ALLOWED' | 'DISABLED'>(
    'ALLOWED',
  )

  const [requestTokenVisible, setRequestTokenVisible] = useState(false)
  const [tvWebhookSecret, setTvWebhookSecret] = useState<string>('')
  const [tvWebhookSecretDraft, setTvWebhookSecretDraft] = useState<string>('')
  const [tvWebhookSecretSource, setTvWebhookSecretSource] = useState<
    'db' | 'env' | 'unset'
  >('unset')
  const [tvWebhookSecretLoaded, setTvWebhookSecretLoaded] = useState(false)
  const [tvWebhookSecretVisible, setTvWebhookSecretVisible] = useState(false)
  const [tvWebhookSecretSaving, setTvWebhookSecretSaving] = useState(false)
  const [tvWebhookSecretError, setTvWebhookSecretError] = useState<string | null>(null)
  const [tvWebhookConfigLoaded, setTvWebhookConfigLoaded] = useState(false)
  const [tvWebhookMode, setTvWebhookMode] = useState<'MANUAL' | 'AUTO'>('MANUAL')
  const [tvWebhookExecutionTarget, setTvWebhookExecutionTarget] = useState<
    'LIVE' | 'PAPER'
  >('LIVE')
  const [tvWebhookBrokerName, setTvWebhookBrokerName] = useState<string>('zerodha')
  const [tvWebhookFallbackToWaiting, setTvWebhookFallbackToWaiting] =
    useState<boolean>(true)
  const [tvWebhookConfigSaving, setTvWebhookConfigSaving] = useState(false)
  const [tvWebhookConfigError, setTvWebhookConfigError] = useState<string | null>(null)

  const [marketExchange, setMarketExchange] = useState<'NSE' | 'BSE'>('NSE')
  const [marketDefaults, setMarketDefaults] = useState<MarketDefaults | null>(null)
  const [marketPreviewDay, setMarketPreviewDay] = useState<string>(() => {
    const d = new Date()
    const yyyy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd}`
  })
  const [marketPreview, setMarketPreview] = useState<ResolvedMarketSession | null>(null)
  const [marketRows, setMarketRows] = useState<MarketCalendarRow[]>([])
  const [marketUploadBusy, setMarketUploadBusy] = useState(false)
  const [marketUploadStatus, setMarketUploadStatus] = useState<string | null>(null)
  const [marketUploadError, setMarketUploadError] = useState<string | null>(null)
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
    const normalizedTab = tab === 'strategy' ? 'webhook' : tab
    if (
      normalizedTab === 'broker' ||
      normalizedTab === 'risk' ||
      normalizedTab === 'webhook' ||
      normalizedTab === 'market' ||
      normalizedTab === 'time'
    ) {
      if (normalizedTab !== activeTab) setActiveTab(normalizedTab as SettingsTab)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search])

  useEffect(() => {
    if (activeTab !== 'webhook' || tvWebhookSecretLoaded) return
    void (async () => {
      try {
        const data = await fetchTradingViewWebhookSecret()
        setTvWebhookSecret(data.value ?? '')
        setTvWebhookSecretDraft(data.value ?? '')
        setTvWebhookSecretSource(data.source)
        setTvWebhookSecretError(null)
        setTvWebhookSecretLoaded(true)
      } catch (err) {
        setTvWebhookSecretError(
          err instanceof Error ? err.message : 'Failed to load webhook secret',
        )
      }
    })()
  }, [activeTab, tvWebhookSecretLoaded])

  useEffect(() => {
    if (activeTab !== 'webhook' || tvWebhookConfigLoaded) return
    void (async () => {
      try {
        const data = await fetchTradingViewWebhookConfig()
        setTvWebhookMode(data.mode)
        setTvWebhookBrokerName(data.broker_name ?? 'zerodha')
        setTvWebhookExecutionTarget(data.execution_target)
        setTvWebhookFallbackToWaiting(Boolean(data.fallback_to_waiting_on_error))
        setTvWebhookConfigError(null)
        setTvWebhookConfigLoaded(true)
      } catch (err) {
        setTvWebhookConfigError(
          err instanceof Error ? err.message : 'Failed to load webhook settings',
        )
      }
    })()
  }, [activeTab, tvWebhookConfigLoaded])

  useEffect(() => {
    if (activeTab !== 'market') return
    let active = true
    void (async () => {
      try {
        const defs = await fetchMarketDefaults()
        const preview = await resolveMarketSession(marketExchange, marketPreviewDay)
        const rows = await listMarketCalendarRows({
          exchange: marketExchange,
          limit: 50,
        })
        if (!active) return
        setMarketDefaults(defs)
        setMarketPreview(preview)
        setMarketRows(rows)
        setMarketUploadError(null)
      } catch (err) {
        if (!active) return
        setMarketUploadError(
          err instanceof Error ? err.message : 'Failed to load market configuration',
        )
      }
    })()
    return () => {
      active = false
    }
  }, [activeTab, marketExchange, marketPreviewDay])

  const handleTabChange = (_event: React.SyntheticEvent, next: string) => {
    const nextTab: SettingsTab =
      next === 'risk'
        ? 'risk'
        : next === 'webhook'
          ? 'webhook'
          : next === 'market'
            ? 'market'
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

  const handleMarketUpload = async (file: File) => {
    setMarketUploadBusy(true)
    setMarketUploadStatus(null)
    setMarketUploadError(null)
    try {
      const res = await uploadMarketCalendarCsv(marketExchange, file)
      setMarketUploadStatus(
        `Imported: ${res.inserted} inserted, ${res.updated} updated`,
      )
      const preview = await resolveMarketSession(marketExchange, marketPreviewDay)
      const rows = await listMarketCalendarRows({ exchange: marketExchange, limit: 50 })
      setMarketPreview(preview)
      setMarketRows(rows)
    } catch (err) {
      setMarketUploadError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setMarketUploadBusy(false)
    }
  }

  const handleMarketDownload = async () => {
    try {
      const blob = await downloadMarketCalendarCsv(marketExchange)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `market_calendar_${marketExchange}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setMarketUploadError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const riskData = await fetchRiskSettings()
        if (!active) return
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

  const handleSaveRiskSettings = async () => {
    try {
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
        strategy_id: null,
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
        Manage TradingView webhook, risk settings, and broker connection details.
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
          <Tab value="webhook" label="TradingView webhook" />
          <Tab value="market" label="Market configuration" />
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

      {activeTab === 'market' && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6">Market Configuration</Typography>
            <Tooltip title="Upload a CSV holiday/session calendar for an exchange. The runtime uses this to decide market hours, proxy close, and buy/sell windows.">
              <IconButton size="small" aria-label="market config help">
                <HelpOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>

          <Typography variant="body2" color="text.secondary">
            Defaults apply unless a specific session override exists in your uploaded CSV.
          </Typography>

          <Paper sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
              <TextField
                select
                size="small"
                label="Exchange"
                value={marketExchange}
                onChange={(e) => setMarketExchange(e.target.value as 'NSE' | 'BSE')}
                sx={{ minWidth: 140 }}
              >
                <MenuItem value="NSE">NSE</MenuItem>
                <MenuItem value="BSE">BSE</MenuItem>
              </TextField>
              <TextField
                size="small"
                type="date"
                label="Preview date"
                value={marketPreviewDay}
                onChange={(e) => setMarketPreviewDay(e.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ minWidth: 180 }}
              />

              <Button variant="outlined" component="label" disabled={marketUploadBusy}>
                {marketUploadBusy ? 'Uploading…' : 'Upload CSV'}
                <input
                  hidden
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (!f) return
                    void handleMarketUpload(f)
                    e.currentTarget.value = ''
                  }}
                />
              </Button>
              <Button
                variant="outlined"
                startIcon={<FileDownloadIcon />}
                onClick={() => void handleMarketDownload()}
              >
                Download CSV
              </Button>
            </Box>

            {marketDefaults && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', mt: 1 }}
              >
                Timezone: {marketDefaults.timezone} | Default session:{' '}
                {marketDefaults.market_open}–{marketDefaults.market_close}
              </Typography>
            )}
            {marketUploadStatus && (
              <Typography
                variant="caption"
                color="success.main"
                sx={{ display: 'block', mt: 1 }}
              >
                {marketUploadStatus}
              </Typography>
            )}
            {marketUploadError && (
              <Typography
                variant="caption"
                color="error"
                sx={{ display: 'block', mt: 1 }}
              >
                {marketUploadError}
              </Typography>
            )}
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Resolved session preview
            </Typography>
            {marketPreview ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                <Typography variant="body2">
                  {marketPreview.exchange} {marketPreview.date}:{' '}
                  {marketPreview.session_type}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Open/Close: {marketPreview.open_time ?? '—'}–
                  {marketPreview.close_time ?? '—'} | Proxy close:{' '}
                  {marketPreview.proxy_close_time ?? '—'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Preferred sell window: {marketPreview.preferred_sell_window[0] ?? '—'}–
                  {marketPreview.preferred_sell_window[1] ?? '—'} | Preferred buy
                  window: {marketPreview.preferred_buy_window[0] ?? '—'}–
                  {marketPreview.preferred_buy_window[1] ?? '—'}
                </Typography>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Loading preview…
              </Typography>
            )}
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Calendar rows (latest 50)
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Date</TableCell>
                  <TableCell>Session</TableCell>
                  <TableCell>Open</TableCell>
                  <TableCell>Close</TableCell>
                  <TableCell>Notes</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {marketRows.map((r) => (
                  <TableRow key={`${r.exchange}:${r.date}`}>
                    <TableCell>{r.date}</TableCell>
                    <TableCell>{r.session_type}</TableCell>
                    <TableCell>{r.open_time ?? '—'}</TableCell>
                    <TableCell>{r.close_time ?? '—'}</TableCell>
                    <TableCell>{r.notes ?? ''}</TableCell>
                  </TableRow>
                ))}
                {marketRows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography variant="caption" color="text.secondary">
                        No calendar rows found for {marketExchange}. Defaults will apply.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        </Box>
      )}

      {activeTab === 'market' ? null : activeTab === 'time' ? (
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
              : activeTab === 'webhook'
                ? 'Loading webhook settings...'
                : 'Loading settings...'}
          </Typography>
        </Box>
      ) : activeTab !== 'broker' && error ? (
        <Typography color="error" variant="body2">
          {error}
        </Typography>
      ) : activeTab === 'webhook' ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mb: 3 }}>
            <Paper sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="h6" sx={{ flex: 1, minWidth: 220 }}>
                  TradingView webhook
                </Typography>
                <Chip
                  size="small"
                  label={`Secret source: ${tvWebhookSecretSource}`}
                  color={tvWebhookSecretSource === 'db' ? 'success' : 'default'}
                />
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1.5 }}>
                Used to authenticate incoming alerts at <code>/webhook/tradingview</code>. You can
                send it either in the JSON payload as <code>secret</code> or via the header{' '}
                <code>X-SIGMATRADER-SECRET</code>.
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                <TextField
                  size="small"
                  label="TradingView webhook secret"
                  type={tvWebhookSecretVisible ? 'text' : 'password'}
                  value={tvWebhookSecretDraft}
                  onChange={(e) => setTvWebhookSecretDraft(e.target.value)}
                  sx={{ minWidth: 320, flex: 1 }}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          size="small"
                          aria-label="toggle TradingView webhook secret visibility"
                          onClick={() => setTvWebhookSecretVisible((prev) => !prev)}
                          edge="end"
                        >
                          {tvWebhookSecretVisible ? 'Hide' : 'Show'}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />
                <Button
                  size="small"
                  variant="outlined"
                  disabled={tvWebhookSecretSaving || tvWebhookSecretDraft === tvWebhookSecret}
                  onClick={() => setTvWebhookSecretDraft(tvWebhookSecret)}
                >
                  Reset
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  disabled={tvWebhookSecretSaving || tvWebhookSecretDraft === tvWebhookSecret}
                  onClick={async () => {
                    setTvWebhookSecretSaving(true)
                    try {
                      const data = await updateTradingViewWebhookSecret(tvWebhookSecretDraft)
                      setTvWebhookSecret(data.value ?? '')
                      setTvWebhookSecretDraft(data.value ?? '')
                      setTvWebhookSecretSource(data.source)
                      setTvWebhookSecretError(null)
                    } catch (err) {
                      setTvWebhookSecretError(
                        err instanceof Error ? err.message : 'Failed to update webhook secret',
                      )
                    } finally {
                      setTvWebhookSecretSaving(false)
                    }
                  }}
                >
                  {tvWebhookSecretSaving ? 'Saving…' : 'Save'}
                </Button>
              </Box>
              {tvWebhookSecretError && (
                <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
                  {tvWebhookSecretError}
                </Typography>
              )}
            </Paper>

            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Routing
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Controls what happens after an alert is converted into an order. AUTO attempts to
                dispatch immediately; MANUAL places it into the Waiting Queue. Risk settings apply
                on dispatch.
              </Typography>
              <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                <TextField
                  select
                  size="small"
                  label="Mode"
                  value={tvWebhookMode}
                  onChange={(e) => setTvWebhookMode(e.target.value as 'MANUAL' | 'AUTO')}
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="MANUAL">MANUAL</MenuItem>
                  <MenuItem value="AUTO">AUTO</MenuItem>
                </TextField>
                <TextField
                  select
                  size="small"
                  label="Execution target"
                  value={tvWebhookExecutionTarget}
                  onChange={(e) => setTvWebhookExecutionTarget(e.target.value as 'LIVE' | 'PAPER')}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="LIVE">LIVE</MenuItem>
                  <MenuItem value="PAPER">PAPER</MenuItem>
                </TextField>
                <TextField
                  select
                  size="small"
                  label="Broker"
                  value={tvWebhookBrokerName}
                  onChange={(e) => setTvWebhookBrokerName(e.target.value)}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="zerodha">Zerodha (Kite)</MenuItem>
                  <MenuItem value="angelone">AngelOne (SmartAPI)</MenuItem>
                </TextField>
                <TextField
                  select
                  size="small"
                  label="On AUTO failure"
                  value={tvWebhookFallbackToWaiting ? 'WAITING' : 'FAIL'}
                  onChange={(e) => setTvWebhookFallbackToWaiting(e.target.value === 'WAITING')}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="WAITING">Move to Waiting Queue</MenuItem>
                  <MenuItem value="FAIL">Keep as failed</MenuItem>
                </TextField>
                <Button
                  size="small"
                  variant="contained"
                  disabled={tvWebhookConfigSaving}
                  onClick={async () => {
                    setTvWebhookConfigSaving(true)
                    try {
                      await updateTradingViewWebhookConfig({
                        mode: tvWebhookMode,
                        broker_name: tvWebhookBrokerName,
                        execution_target: tvWebhookExecutionTarget,
                        fallback_to_waiting_on_error: tvWebhookFallbackToWaiting,
                      })
                      setTvWebhookConfigError(null)
                    } catch (err) {
                      setTvWebhookConfigError(
                        err instanceof Error ? err.message : 'Failed to save webhook settings',
                      )
                    } finally {
                      setTvWebhookConfigSaving(false)
                    }
                  }}
                >
                  {tvWebhookConfigSaving ? 'Saving…' : 'Save'}
                </Button>
              </Box>
              {tvWebhookConfigError && (
                <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
                  {tvWebhookConfigError}
                </Typography>
              )}
            </Paper>
          </Box>
      ) : activeTab === 'risk' ? (
          <Paper sx={{ mb: 3, p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Risk Settings
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Define global limits. Leave fields blank to skip a particular limit; new rows are
              added to the table below.
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
                  <TableCell>Max Order Value</TableCell>
                  <TableCell>Max Qty/Order</TableCell>
                  <TableCell>Max Daily Loss</TableCell>
                  <TableCell>Clamp Mode</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {riskSettings.filter((rs) => rs.scope === 'GLOBAL').map((rs) => (
                  <TableRow key={rs.id}>
                    <TableCell>{rs.scope}</TableCell>
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
                {riskSettings.filter((rs) => rs.scope === 'GLOBAL').length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6}>
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
