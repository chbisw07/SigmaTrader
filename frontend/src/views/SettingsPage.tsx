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
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Switch from '@mui/material/Switch'
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

import { RiskHelpDrawer } from '../components/RiskHelpDrawer'
import { SETTINGS_HELP_BY_TAB } from '../help/risk/contexts'

import {
  fetchRiskPolicy,
  resetRiskPolicy,
  updateRiskPolicy,
  type OrderSourceBucket,
  type ProductType,
  type RiskPolicy,
} from '../services/riskPolicy'

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
import { TradingViewAlertPayloadBuilder } from '../components/TradingViewAlertPayloadBuilder'
import { RiskEngineV2Settings } from '../components/RiskEngineV2Settings'
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


function HelpTip({
  title,
}: {
  title: string
}) {
  return (
    <Tooltip title={title} arrow placement="top">
      <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center' }}>
        <HelpOutlineIcon
          sx={{ fontSize: 16, color: 'text.secondary', cursor: 'help' }}
        />
      </Box>
    </Tooltip>
  )
}

function LabelWithHelp({
  label,
  help,
}: {
  label: string
  help?: string
}) {
  return (
    <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
      <span>{label}</span>
      {help ? <HelpTip title={help} /> : null}
    </Box>
  )
}

function RiskGroupHeader({
  groupId,
  title,
  help,
  description,
  globalEnabled,
  groupEnabled,
  notEnforcedYet,
  onToggle,
}: {
  groupId?: string
  title: string
  help?: string
  description: string
  globalEnabled: boolean
  groupEnabled: boolean
  notEnforcedYet?: boolean
  onToggle: (checked: boolean) => void
}) {
  const enforced = Boolean(globalEnabled && groupEnabled)
  return (
    <Box
      data-testid={groupId ? `risk-group-${groupId}` : undefined}
      sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}
    >
      <Box sx={{ flex: 1, minWidth: 260 }}>
        <Typography
          variant="subtitle2"
          sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}
        >
          {title}
          {help ? <HelpTip title={help} /> : null}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
          {description}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        {notEnforcedYet ? (
          <Chip size="small" color="warning" label="Not enforced yet" />
        ) : null}
        <Chip
          size="small"
          color={enforced ? 'success' : 'default'}
          label={enforced ? 'Enforced' : 'Configured, not enforced'}
        />
        <FormControlLabel
          control={<Switch checked={groupEnabled} onChange={(e) => onToggle(e.target.checked)} />}
          label="Enforce this group"
        />
      </Box>
    </Box>
  )
}

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

  const [riskPolicyLoaded, setRiskPolicyLoaded] = useState(false)
  const [riskPolicySource, setRiskPolicySource] = useState<'db' | 'default'>('default')
  const [riskPolicyDraft, setRiskPolicyDraft] = useState<RiskPolicy | null>(null)
  const [riskPolicyBusy, setRiskPolicyBusy] = useState(false)
  const [riskPolicyError, setRiskPolicyError] = useState<string | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)

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
    if (activeTab !== 'risk' || riskPolicyLoaded) return
    let active = true
    void (async () => {
      try {
        const data = await fetchRiskPolicy()
        if (!active) return
        setRiskPolicySource(data.source)
        setRiskPolicyDraft(JSON.parse(JSON.stringify(data.policy)) as RiskPolicy)
        setRiskPolicyError(null)
        setRiskPolicyLoaded(true)
      } catch (err) {
        if (!active) return
        setRiskPolicyError(
          err instanceof Error ? err.message : 'Failed to load risk policy',
        )
      }
    })()
    return () => {
      active = false
    }
  }, [activeTab, riskPolicyLoaded])

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

  return (
    <Box>
      <RiskHelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        context={SETTINGS_HELP_BY_TAB[activeTab]}
      />
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
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          flexWrap: 'wrap',
        }}
      >
        <Typography variant="h4" gutterBottom>
          Settings
        </Typography>
        <Button size="small" variant="outlined" onClick={() => navigate('/risk-guide')}>
          Risk management guide
        </Button>
      </Box>
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
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" sx={{ flex: 1 }}>
              Broker Settings
            </Typography>
            <Tooltip title="Help" arrow placement="top">
              <IconButton size="small" onClick={() => setHelpOpen(true)} aria-label="broker help">
                <HelpOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
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
            <Tooltip title="Help" arrow placement="top">
              <IconButton
                size="small"
                aria-label="market configuration help"
                onClick={() => setHelpOpen(true)}
              >
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
      ) : activeTab === 'webhook' ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mb: 3 }}>
            <Paper sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="h6" sx={{ flex: 1, minWidth: 220 }}>
                  TradingView webhook
                </Typography>
                <Tooltip title="Help" arrow placement="top">
                  <IconButton
                    size="small"
                    onClick={() => setHelpOpen(true)}
                    aria-label="TradingView webhook help"
                  >
                    <HelpOutlineIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
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

            <TradingViewAlertPayloadBuilder webhookSecret={tvWebhookSecretDraft} />
          </Box>
      ) : activeTab === 'risk' ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mb: 3 }}>
            <RiskEngineV2Settings />
            <Paper sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="h6" sx={{ flex: 1, minWidth: 220 }}>
                  Risk policy
                </Typography>
                <Tooltip title="Help" arrow placement="top">
                  <IconButton
                    size="small"
                    onClick={() => setHelpOpen(true)}
                    aria-label="risk management help"
                  >
                    <HelpOutlineIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Chip
                  size="small"
                  label={`Source: ${riskPolicySource}`}
                  color={riskPolicySource === 'db' ? 'success' : 'default'}
                />
              </Box>
              {!riskPolicyLoaded || !riskPolicyDraft ? (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
                  <CircularProgress size={20} />
                  <Typography variant="body2">Loading risk policy…</Typography>
                </Box>
              ) : (
                <>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    Enforced at order dispatch/execute time (manual queue, TradingView AUTO, deployments).
                  </Typography>

                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mt: 1.5 }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.enabled}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev ? { ...prev, enabled: e.target.checked } : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Enable enforcement"
                          help="When enabled, SigmaTrader blocks/clamps orders at dispatch/execute time (manual queue, TradingView AUTO, deployments)."
                        />
                      }
                    />
                    <Button
                      size="small"
                      variant="contained"
                      disabled={riskPolicyBusy}
                      onClick={async () => {
                        if (!riskPolicyDraft) return
                        setRiskPolicyBusy(true)
                        try {
                          const updated = await updateRiskPolicy(riskPolicyDraft)
                          setRiskPolicyDraft(JSON.parse(JSON.stringify(updated)) as RiskPolicy)
                          setRiskPolicySource('db')
                          setRiskPolicyError(null)
                        } catch (err) {
                          setRiskPolicyError(
                            err instanceof Error ? err.message : 'Failed to save risk policy',
                          )
                        } finally {
                          setRiskPolicyBusy(false)
                        }
                      }}
                    >
                      {riskPolicyBusy ? 'Saving…' : 'Save'}
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={riskPolicyBusy}
                      onClick={async () => {
                        const confirmed = window.confirm('Reset risk policy to defaults?')
                        if (!confirmed) return
                        setRiskPolicyBusy(true)
                        try {
                          const defaults = await resetRiskPolicy()
                          setRiskPolicyDraft(JSON.parse(JSON.stringify(defaults)) as RiskPolicy)
                          setRiskPolicySource('db')
                          setRiskPolicyError(null)
                        } catch (err) {
                          setRiskPolicyError(
                            err instanceof Error ? err.message : 'Failed to reset risk policy',
                          )
                        } finally {
                          setRiskPolicyBusy(false)
                        }
                      }}
                    >
                      Reset to defaults
                    </Button>
                  </Box>

                  {riskPolicyError && (
                    <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
                      {riskPolicyError}
                    </Typography>
                  )}

                  <Divider sx={{ my: 2 }} />

                  <Typography
                    variant="subtitle2"
                    sx={{
                      mb: 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.75,
                    }}
                  >
                    Equity baseline (manual)
                    <HelpTip title="This equity is the baseline for all % limits (daily loss %, risk per trade %, order value %, exposure %). It is not fetched from the broker yet." />
                  </Typography>
                  <TextField
                    size="small"
                    type="number"
                    label={
                      <LabelWithHelp
                        label="Manual equity (INR)"
                        help="Used as the primary equity baseline for risk calculations. Example: with 1,000,000 INR equity and 0.5% risk per trade, max risk per trade is 5,000 INR."
                      />
                    }
                    value={riskPolicyDraft.equity.manual_equity_inr}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      if (!Number.isFinite(v)) return
                      setRiskPolicyDraft((prev) =>
                        prev ? { ...prev, equity: { ...prev.equity, manual_equity_inr: v } } : prev,
                      )
                    }}
                    sx={{ minWidth: 260 }}
                  />

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="account_level"
                    title="Account-level risk"
                    help="Account-wide limits evaluated at execution time using cached positions/snapshots."
                    description="Daily loss, max open positions/symbols, and exposure caps."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.account_level}
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev
                          ? { ...prev, enforcement: { ...prev.enforcement, account_level: checked } }
                          : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max daily loss (%)"
                          help="HARD STOP. If today's PnL is <= -(% of equity), new executions are rejected. Uses cached position PnL (PositionSnapshot/Position)."
                        />
                      }
                      value={riskPolicyDraft.account_risk.max_daily_loss_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, account_risk: { ...prev.account_risk, max_daily_loss_pct: v } }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max daily loss (abs INR)"
                          help="Optional HARD STOP override. If set, this absolute INR limit is used (instead of deriving from equity + %)."
                        />
                      }
                      value={riskPolicyDraft.account_risk.max_daily_loss_abs ?? ''}
                      onChange={(e) => {
                        const raw = e.target.value
                        const v = raw.trim() === '' ? null : Number(raw)
                        if (v !== null && !Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, account_risk: { ...prev.account_risk, max_daily_loss_abs: v } }
                            : prev,
                        )
                      }}
                      helperText="Blank = auto from equity + %"
                      sx={{ minWidth: 220 }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max open positions"
                          help="Rejects executions once the number of open positions (non-zero qty in cached positions table) reaches this limit."
                        />
                      }
                      value={riskPolicyDraft.account_risk.max_open_positions}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, account_risk: { ...prev.account_risk, max_open_positions: v } }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max concurrent symbols"
                          help="Rejects executions once the number of distinct symbols held concurrently reaches this limit (based on cached positions)."
                        />
                      }
                      value={riskPolicyDraft.account_risk.max_concurrent_symbols}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, account_risk: { ...prev.account_risk, max_concurrent_symbols: v } }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max exposure (%)"
                          help="Total deployed capital cap. Blocks BUY orders if estimated exposure (sum(|qty×avg_price|) + this order value) exceeds % of equity."
                        />
                      }
                      value={riskPolicyDraft.account_risk.max_exposure_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, account_risk: { ...prev.account_risk, max_exposure_pct: v } }
                            : prev,
                        )
                      }}
                    />
                  </Box>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="per_trade"
                    title="Per-trade risk"
                    help="Sizing checks clamp quantity so worst-case loss (qty × stop distance) stays within % of equity."
                    description="Per-trade risk caps and stop-loss mandatory sizing rule."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.per_trade}
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev
                          ? { ...prev, enforcement: { ...prev.enforcement, per_trade: checked } }
                          : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max risk per trade (%)"
                          help="Default target risk per trade. Qty is clamped so (qty × stop_distance) ≤ this % of equity."
                        />
                      }
                      value={riskPolicyDraft.trade_risk.max_risk_per_trade_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, trade_risk: { ...prev.trade_risk, max_risk_per_trade_pct: v } }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Hard max risk (%)"
                          help="Absolute ceiling. Even if other settings allow higher risk, qty is clamped to never exceed this % of equity."
                        />
                      }
                      value={riskPolicyDraft.trade_risk.hard_max_risk_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, trade_risk: { ...prev.trade_risk, hard_max_risk_pct: v } }
                            : prev,
                        )
                      }}
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.trade_risk.stop_loss_mandatory}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    trade_risk: { ...prev.trade_risk, stop_loss_mandatory: e.target.checked },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Stop mandatory"
                          help="If enabled and SigmaTrader cannot estimate stop distance (missing price/candles), the execution is rejected."
                        />
                      }
                    />
                  </Box>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="position_sizing"
                    title="Position sizing"
                    help="Caps how big a single order can be (SigmaTrader clamps qty; it does not derive a new qty from scratch)."
                    description="Capital per trade cap, scale-in toggle, and pyramiding limit."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.position_sizing}
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev
                          ? {
                              ...prev,
                              enforcement: { ...prev.enforcement, position_sizing: checked },
                            }
                          : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Capital per trade (INR)"
                          help="Additional per-order value cap in INR. If an order exceeds this amount, qty is clamped (and rejected if it would become < 1 share)."
                        />
                      }
                      value={riskPolicyDraft.position_sizing.capital_per_trade}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, position_sizing: { ...prev.position_sizing, capital_per_trade: v } }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label="Max order value (% of equity)"
                      value={riskPolicyDraft.execution_safety.max_order_value_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, execution_safety: { ...prev.execution_safety, max_order_value_pct: v } }
                            : prev,
                        )
                      }}
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.position_sizing.allow_scale_in}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    position_sizing: {
                                      ...prev.position_sizing,
                                      allow_scale_in: e.target.checked,
                                    },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Allow scale-in"
                          help="Enforced. Controls whether adding to an existing position is allowed."
                        />
                      }
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Pyramiding"
                          help="Enforced. Caps the number of entries per symbol while a position is open."
                        />
                      }
                      value={riskPolicyDraft.position_sizing.pyramiding}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, position_sizing: { ...prev.position_sizing, pyramiding: v } }
                            : prev,
                        )
                      }}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    Scale-in applies only when a position already exists. Keep positions synced for
                    accurate enforcement.
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="stop_rules"
                    title="Stop rules & managed exits"
                    help="Used for sizing checks and SigmaTrader-managed stop/trailing exits. No broker-side SL/TP orders are placed."
                    description="Stop basis, ATR/fixed stop distance rules, and trailing activation (app-managed)."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.stop_rules}
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev ? { ...prev, enforcement: { ...prev.enforcement, stop_rules: checked } } : prev,
                      )
                    }
                  />
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Choose how SigmaTrader estimates stop distance for risk sizing checks.
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      select
                      size="small"
                      label={
                        <LabelWithHelp
                          label="Stop basis"
                          help="Select how stop distance is estimated for sizing checks."
                        />
                      }
                      value={riskPolicyDraft.trade_risk.stop_reference}
                      onChange={(e) => {
                        const v = e.target.value as 'ATR' | 'FIXED_PCT'
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, trade_risk: { ...prev.trade_risk, stop_reference: v } }
                            : prev,
                        )
                      }}
                      sx={{ minWidth: 220 }}
                    >
                      <MenuItem value="ATR">ATR (volatility-based)</MenuItem>
                      <MenuItem value="FIXED_PCT">Fixed percent</MenuItem>
                    </TextField>
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Min stop (%)"
                          help="Lower bound for stop distance as % of price (prevents unrealistically tight stops for sizing checks)."
                        />
                      }
                      value={riskPolicyDraft.stop_rules.min_stop_distance_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, stop_rules: { ...prev.stop_rules, min_stop_distance_pct: v } }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max stop (%)"
                          help="Upper bound for stop distance as % of price (prevents excessively loose stops for sizing checks)."
                        />
                      }
                      value={riskPolicyDraft.stop_rules.max_stop_distance_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, stop_rules: { ...prev.stop_rules, max_stop_distance_pct: v } }
                            : prev,
                        )
                      }}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    {riskPolicyDraft.trade_risk.stop_reference === 'ATR'
                      ? 'ATR scales with volatility and adapts to changing market conditions.'
                      : 'Fixed percent uses a constant percent of price, which can be easier to reason about.'}
                  </Typography>
                  {riskPolicyDraft.trade_risk.stop_reference === 'ATR' ? (
                    <Box
                      sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mt: 1 }}
                    >
                      <TextField
                        size="small"
                        type="number"
                        label={
                          <LabelWithHelp
                            label="ATR period"
                            help="Lookback period in bars for the ATR calculation."
                          />
                        }
                        value={riskPolicyDraft.stop_rules.atr_period}
                        onChange={(e) => {
                          const v = Number(e.target.value)
                          if (!Number.isFinite(v)) return
                          setRiskPolicyDraft((prev) =>
                            prev
                              ? { ...prev, stop_rules: { ...prev.stop_rules, atr_period: v } }
                              : prev,
                          )
                        }}
                      />
                      <TextField
                        size="small"
                        type="number"
                        label={
                          <LabelWithHelp
                            label="ATR stop (xATR)"
                            help="Stop distance is ATR times this multiplier."
                          />
                        }
                        value={riskPolicyDraft.stop_rules.initial_stop_atr}
                        onChange={(e) => {
                          const v = Number(e.target.value)
                          if (!Number.isFinite(v)) return
                          setRiskPolicyDraft((prev) =>
                            prev
                              ? { ...prev, stop_rules: { ...prev.stop_rules, initial_stop_atr: v } }
                              : prev,
                          )
                        }}
                      />
                      <TextField
                        size="small"
                        type="number"
                        label={
                          <LabelWithHelp
                            label="Fallback stop (%)"
                            help="Used when ATR data is unavailable."
                          />
                        }
                        value={riskPolicyDraft.stop_rules.fallback_stop_pct}
                        onChange={(e) => {
                          const v = Number(e.target.value)
                          if (!Number.isFinite(v)) return
                          setRiskPolicyDraft((prev) =>
                            prev
                              ? { ...prev, stop_rules: { ...prev.stop_rules, fallback_stop_pct: v } }
                              : prev,
                          )
                        }}
                      />
                    </Box>
                  ) : (
                    <Box
                      sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mt: 1 }}
                    >
                      <TextField
                        size="small"
                        type="number"
                        label={
                          <LabelWithHelp
                            label="Fixed stop (%)"
                            help="Stop distance as a fixed percent of price."
                          />
                        }
                        value={riskPolicyDraft.stop_rules.fallback_stop_pct}
                        onChange={(e) => {
                          const v = Number(e.target.value)
                          if (!Number.isFinite(v)) return
                          setRiskPolicyDraft((prev) =>
                            prev
                              ? { ...prev, stop_rules: { ...prev.stop_rules, fallback_stop_pct: v } }
                              : prev,
                          )
                        }}
                      />
                    </Box>
                  )}
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mt: 1 }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.stop_rules.trailing_stop_enabled}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    stop_rules: {
                                      ...prev.stop_rules,
                                      trailing_stop_enabled: e.target.checked,
                                    },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Trailing enabled"
                          help="Controls future trailing-stop automation."
                        />
                      }
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label={
                            riskPolicyDraft.trade_risk.stop_reference === 'ATR'
                              ? 'Trail activation (xATR)'
                              : 'Trail activation (%)'
                          }
                          help={
                            riskPolicyDraft.trade_risk.stop_reference === 'ATR'
                              ? 'Starts trailing only after price moves in favor by this many ATRs.'
                              : 'Starts trailing only after price moves in favor by this percent.'
                          }
                        />
                      }
                      value={
                        riskPolicyDraft.trade_risk.stop_reference === 'ATR'
                          ? riskPolicyDraft.stop_rules.trail_activation_atr
                          : riskPolicyDraft.stop_rules.trail_activation_pct
                      }
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                stop_rules: {
                                  ...prev.stop_rules,
                                  ...(prev.trade_risk.stop_reference === 'ATR'
                                    ? { trail_activation_atr: v }
                                    : { trail_activation_pct: v }),
                                },
                              }
                            : prev,
                        )
                      }}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    Stops and trailing exits are enforced by SigmaTrader (app-managed). Keep SigmaTrader
                    running.
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="trade_frequency"
                    title="Trade frequency"
                    help="Overtrading protection at execute time per (user, strategy/deployment, symbol, product) using persisted state (IST day)."
                    description="Max trades/day, min bars between trades, cooldown after loss (bars)."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.trade_frequency}
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev
                          ? { ...prev, enforcement: { ...prev.enforcement, trade_frequency: checked } }
                          : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max trades/symbol/day"
                          help="Enforced at execute time. Blocks further executions for the same scope key after this many executions in the current IST day."
                        />
                      }
                      value={riskPolicyDraft.trade_frequency.max_trades_per_symbol_per_day}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                trade_frequency: {
                                  ...prev.trade_frequency,
                                  max_trades_per_symbol_per_day: v,
                                },
                              }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Min bars between trades"
                          help="Enforced at execute time. Uses time-derived bars based on TradingView interval (or a default interval when unknown)."
                        />
                      }
                      value={riskPolicyDraft.trade_frequency.min_bars_between_trades}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                trade_frequency: {
                                  ...prev.trade_frequency,
                                  min_bars_between_trades: v,
                                },
                              }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Cooldown after loss (bars)"
                          help="Enforced at execute time. After a losing close, blocks new executions for N bars."
                        />
                      }
                      value={riskPolicyDraft.trade_frequency.cooldown_after_loss_bars}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                trade_frequency: {
                                  ...prev.trade_frequency,
                                  cooldown_after_loss_bars: v,
                                },
                              }
                            : prev,
                        )
                      }}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    Enforced at execution layer when global enforcement is enabled and this group is enabled.
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="loss_controls"
                    title="Loss controls"
                    help="Protects against drawdowns/loss streaks. Enforced at execute time using persisted state."
                    description="Loss streak counting and pause-after-streak (EOD) behavior."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.loss_controls}
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev ? { ...prev, enforcement: { ...prev.enforcement, loss_controls: checked } } : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max consecutive losses"
                          help="Enforced. Counts consecutive losing closes per scope key."
                        />
                      }
                      value={riskPolicyDraft.loss_controls.max_consecutive_losses}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                loss_controls: { ...prev.loss_controls, max_consecutive_losses: v },
                              }
                            : prev,
                        )
                      }}
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.loss_controls.pause_after_loss_streak}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    loss_controls: {
                                      ...prev.loss_controls,
                                      pause_after_loss_streak: e.target.checked,
                                    },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Pause after streak"
                          help="Enforced. When enabled, blocks new executions after the loss streak threshold is hit."
                        />
                      }
                    />
                    <TextField
                      size="small"
                      label={
                        <LabelWithHelp
                          label="Pause duration"
                          help="Currently supported: EOD (end of trading day, IST)."
                        />
                      }
                      value={riskPolicyDraft.loss_controls.pause_duration}
                      onChange={(e) =>
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                loss_controls: { ...prev.loss_controls, pause_duration: e.target.value },
                              }
                            : prev,
                        )
                      }
                      sx={{ minWidth: 160 }}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    Enforced at execution layer when global enforcement is enabled and this group is enabled.
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="correlation_controls"
                    title="Correlation & symbol controls"
                    help="Intended to help avoid concentration in correlated sectors/symbols."
                    description="Sector/correlation-based limits (not enforced by backend yet)."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.correlation_controls}
                    notEnforcedYet
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev
                          ? {
                              ...prev,
                              enforcement: { ...prev.enforcement, correlation_controls: checked },
                            }
                          : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max same-sector positions"
                          help="Intended to cap the number of open positions from the same sector/theme."
                        />
                      }
                      value={riskPolicyDraft.correlation_rules.max_same_sector_positions}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                correlation_rules: {
                                  ...prev.correlation_rules,
                                  max_same_sector_positions: v,
                                },
                              }
                            : prev,
                        )
                      }}
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Sector correlation limit"
                          help="Intended to block adding positions when correlation exceeds this threshold."
                        />
                      }
                      value={riskPolicyDraft.correlation_rules.sector_correlation_limit}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                correlation_rules: {
                                  ...prev.correlation_rules,
                                  sector_correlation_limit: v,
                                },
                              }
                            : prev,
                        )
                      }}
                    />
                  </Box>
                  <Typography variant="caption" color="error" sx={{ mt: 0.5, display: 'block' }}>
                    Correlation and sector controls are not enforced yet.
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="execution_safety"
                    title="Execution safety"
                    help="Execution-layer guardrails. Product gates and order caps are enforced before broker submission."
                    description="Product allow/deny, short-selling gate, order value caps, and (planned) margin checks."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.execution_safety}
                    notEnforcedYet
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev
                          ? {
                              ...prev,
                              enforcement: { ...prev.enforcement, execution_safety: checked },
                            }
                          : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.execution_safety.allow_mis}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? { ...prev, execution_safety: { ...prev.execution_safety, allow_mis: e.target.checked } }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Allow MIS (global)"
                          help="Enforced. If disabled, MIS executions are rejected unless an override allows it."
                        />
                      }
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.execution_safety.allow_cnc}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? { ...prev, execution_safety: { ...prev.execution_safety, allow_cnc: e.target.checked } }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Allow CNC (global)"
                          help="Enforced. If disabled, CNC executions are rejected unless an override allows it."
                        />
                      }
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.execution_safety.allow_short_selling}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    execution_safety: {
                                      ...prev.execution_safety,
                                      allow_short_selling: e.target.checked,
                                    },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Allow short selling (MIS)"
                          help="Enforced. Blocks SELL orders that would open or increase short positions."
                        />
                      }
                    />
                    <TextField
                      size="small"
                      type="number"
                      label={
                        <LabelWithHelp
                          label="Max order value (% of equity)"
                          help="Enforced. Qty is clamped so order value (qty × price) does not exceed this % of equity (also combined with Capital per trade and overrides)."
                        />
                      }
                      value={riskPolicyDraft.execution_safety.max_order_value_pct}
                      onChange={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        setRiskPolicyDraft((prev) =>
                          prev
                            ? { ...prev, execution_safety: { ...prev.execution_safety, max_order_value_pct: v } }
                            : prev,
                        )
                      }}
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.execution_safety.reject_if_margin_exceeded}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    execution_safety: {
                                      ...prev.execution_safety,
                                      reject_if_margin_exceeded: e.target.checked,
                                    },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="Reject if margin exceeded"
                          help="Intended to block orders when broker margin is insufficient."
                        />
                      }
                    />
                  </Box>
                  <Typography variant="caption" color="error" sx={{ mt: 0.5, display: 'block' }}>
                    Margin checks are not enforced yet.
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="emergency_controls"
                    title="Emergency controls"
                    help="Kill-switch style controls. panic_stop is enforced immediately."
                    description="Immediate global stop plus (planned) error-based halts."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.emergency_controls}
                    notEnforcedYet
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev
                          ? { ...prev, enforcement: { ...prev.enforcement, emergency_controls: checked } }
                          : prev,
                      )
                    }
                  />
                  <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.emergency_controls.panic_stop}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    emergency_controls: { ...prev.emergency_controls, panic_stop: e.target.checked },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="panic_stop"
                          help="Enforced. Blocks all executions immediately (global kill switch)."
                        />
                      }
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.emergency_controls.stop_all_trading_on_error}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    emergency_controls: {
                                      ...prev.emergency_controls,
                                      stop_all_trading_on_error: e.target.checked,
                                    },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="stop_all_trading_on_error"
                          help="Intended to stop trading after unexpected broker/system errors."
                        />
                      }
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={riskPolicyDraft.emergency_controls.stop_on_unexpected_qty}
                          onChange={(e) =>
                            setRiskPolicyDraft((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    emergency_controls: {
                                      ...prev.emergency_controls,
                                      stop_on_unexpected_qty: e.target.checked,
                                    },
                                  }
                                : prev,
                            )
                          }
                        />
                      }
                      label={
                        <LabelWithHelp
                          label="stop_on_unexpected_qty"
                          help="Intended to stop trading if order qty changes unexpectedly after normalization/clamping."
                        />
                      }
                    />
                  </Box>
                  <Typography variant="caption" color="error" sx={{ mt: 0.5, display: 'block' }}>
                    Error-based emergency stops are not enforced yet.
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <RiskGroupHeader
                    groupId="overrides"
                    title="Overrides (source/product)"
                    help="Overrides apply different values to TradingView vs SigmaTrader orders, separately for MIS and CNC."
                    description="Overrides change values (caps/gates) but do not override whether groups are enforced."
                    globalEnabled={riskPolicyDraft.enabled}
                    groupEnabled={riskPolicyDraft.enforcement.overrides}
                    onToggle={(checked) =>
                      setRiskPolicyDraft((prev) =>
                        prev ? { ...prev, enforcement: { ...prev.enforcement, overrides: checked } } : prev,
                      )
                    }
                  />
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Leave a field blank to inherit from GLOBAL.
                  </Typography>

                  {(() => {
                    const sources: OrderSourceBucket[] = ['TRADINGVIEW', 'SIGMATRADER']
                    const products: ProductType[] = ['MIS', 'CNC']
                    const setOverride = (
                      source: OrderSourceBucket,
                      product: ProductType,
                      key: string,
                      value: any,
                    ) => {
                      setRiskPolicyDraft((prev) => {
                        if (!prev) return prev
                        const existing = (prev.overrides?.[source]?.[product] ?? {}) as any
                        return {
                          ...prev,
                          overrides: {
                            ...prev.overrides,
                            [source]: {
                              ...prev.overrides[source],
                              [product]: { ...existing, [key]: value },
                            },
                          },
                        }
                      })
                    }

                    return (
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>
                              <LabelWithHelp
                                label="Source"
                                help="Which engine produced the order: TradingView webhooks vs internal SigmaTrader alerts/strategies/deployments."
                              />
                            </TableCell>
                            <TableCell>
                              <LabelWithHelp
                                label="Product"
                                help="MIS vs CNC. Use this to enforce stricter limits for intraday (MIS) compared to delivery (CNC)."
                              />
                            </TableCell>
                            <TableCell>
                              <LabelWithHelp
                                label="Allow"
                                help="DEFAULT inherits from global allow_mis/allow_cnc. You can explicitly ALLOW/DISALLOW for this source+product."
                              />
                            </TableCell>
                            <TableCell>
                              <LabelWithHelp
                                label="Max order value (abs)"
                                help="Absolute INR cap for a single order (applies in addition to % of equity and capital/trade caps)."
                              />
                            </TableCell>
                            <TableCell>
                              <LabelWithHelp
                                label="Max qty/order"
                                help="Hard cap on quantity for a single order."
                              />
                            </TableCell>
                            <TableCell>
                              <LabelWithHelp
                                label="Capital/trade"
                                help="Overrides global Capital per trade for this source+product."
                              />
                            </TableCell>
                            <TableCell>
                              <LabelWithHelp
                                label="Max risk (%)"
                                help="Overrides global max risk per trade for this source+product (qty × stop distance)."
                              />
                            </TableCell>
                            <TableCell>
                              <LabelWithHelp
                                label="Hard max risk (%)"
                                help="Overrides global hard max risk per trade for this source+product (absolute ceiling)."
                              />
                            </TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {sources.flatMap((src) =>
                            products.map((prod) => {
                              const ovr = riskPolicyDraft.overrides?.[src]?.[prod] ?? {}
                              return (
                                <TableRow key={`${src}_${prod}`}>
                                  <TableCell>{src}</TableCell>
                                  <TableCell>{prod}</TableCell>
                                  <TableCell>
                                    <TextField
                                      select
                                      size="small"
                                      value={
                                        ovr.allow === true
                                          ? 'ALLOW'
                                          : ovr.allow === false
                                            ? 'DISALLOW'
                                            : 'DEFAULT'
                                      }
                                      onChange={(e) => {
                                        const v = e.target.value
                                        setOverride(
                                          src,
                                          prod,
                                          'allow',
                                          v === 'ALLOW' ? true : v === 'DISALLOW' ? false : null,
                                        )
                                      }}
                                      sx={{ minWidth: 130 }}
                                    >
                                      <MenuItem value="DEFAULT">DEFAULT</MenuItem>
                                      <MenuItem value="ALLOW">ALLOW</MenuItem>
                                      <MenuItem value="DISALLOW">DISALLOW</MenuItem>
                                    </TextField>
                                  </TableCell>
                                  <TableCell>
                                    <TextField
                                      size="small"
                                      type="number"
                                      value={ovr.max_order_value_abs ?? ''}
                                      onChange={(e) => {
                                        const raw = e.target.value
                                        const v = raw.trim() === '' ? null : Number(raw)
                                        if (v !== null && !Number.isFinite(v)) return
                                        setOverride(src, prod, 'max_order_value_abs', v)
                                      }}
                                      sx={{ minWidth: 170 }}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <TextField
                                      size="small"
                                      type="number"
                                      value={ovr.max_quantity_per_order ?? ''}
                                      onChange={(e) => {
                                        const raw = e.target.value
                                        const v = raw.trim() === '' ? null : Number(raw)
                                        if (v !== null && !Number.isFinite(v)) return
                                        setOverride(src, prod, 'max_quantity_per_order', v)
                                      }}
                                      sx={{ minWidth: 140 }}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <TextField
                                      size="small"
                                      type="number"
                                      value={ovr.capital_per_trade ?? ''}
                                      onChange={(e) => {
                                        const raw = e.target.value
                                        const v = raw.trim() === '' ? null : Number(raw)
                                        if (v !== null && !Number.isFinite(v)) return
                                        setOverride(src, prod, 'capital_per_trade', v)
                                      }}
                                      sx={{ minWidth: 140 }}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <TextField
                                      size="small"
                                      type="number"
                                      value={ovr.max_risk_per_trade_pct ?? ''}
                                      onChange={(e) => {
                                        const raw = e.target.value
                                        const v = raw.trim() === '' ? null : Number(raw)
                                        if (v !== null && !Number.isFinite(v)) return
                                        setOverride(src, prod, 'max_risk_per_trade_pct', v)
                                      }}
                                      sx={{ minWidth: 140 }}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <TextField
                                      size="small"
                                      type="number"
                                      value={ovr.hard_max_risk_pct ?? ''}
                                      onChange={(e) => {
                                        const raw = e.target.value
                                        const v = raw.trim() === '' ? null : Number(raw)
                                        if (v !== null && !Number.isFinite(v)) return
                                        setOverride(src, prod, 'hard_max_risk_pct', v)
                                      }}
                                      sx={{ minWidth: 140 }}
                                    />
                                  </TableCell>
                                </TableRow>
                              )
                            }),
                          )}
                        </TableBody>
                      </Table>
                    )
                  })()}
                </>
              )}
            </Paper>
          </Box>
      ) : null}
    </Box>
  )
}
