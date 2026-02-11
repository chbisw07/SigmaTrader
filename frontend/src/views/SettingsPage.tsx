import FileDownloadIcon from '@mui/icons-material/FileDownload'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
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

import { RiskHelpDrawer } from '../components/RiskHelpDrawer'
import { SETTINGS_HELP_BY_TAB } from '../help/risk/contexts'

import {
  clearZerodhaPostbackFailures,
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
import { RiskProfilesSettings } from '../components/RiskProfilesSettings'
import { HoldingsExitAutomationSettings } from '../components/HoldingsExitAutomationSettings'
import { RiskGlobalsPanel } from '../components/RiskGlobalsPanel'
import { RiskSettingsBackupPanel } from '../components/RiskSettingsBackupPanel'
import { RiskSourceOverridesPanel } from '../components/RiskSourceOverridesPanel'
import { EffectiveRiskSummaryPanel } from '../components/EffectiveRiskSummaryPanel'
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

  const [brokerStatus, setBrokerStatus] = useState<ZerodhaStatus | null>(null)
  const [angeloneStatus, setAngeloneStatus] = useState<AngeloneStatus | null>(null)
  const [zerodhaError, setZerodhaError] = useState<string | null>(null)
  const [angeloneError, setAngeloneError] = useState<string | null>(null)
  const [marketStatus, setMarketStatus] = useState<MarketDataStatus | null>(null)
  const [requestToken, setRequestToken] = useState('')
  const [isConnecting, setIsConnecting] = useState(false)
  const [clearingZerodhaPostbackFailures, setClearingZerodhaPostbackFailures] =
    useState(false)
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
  const [tvWebhookDefaultProduct, setTvWebhookDefaultProduct] = useState<'CNC' | 'MIS'>('CNC')
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
        setTvWebhookDefaultProduct((data.default_product ?? 'CNC') as 'CNC' | 'MIS')
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

  const handleCopyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Ignore; clipboard may be unavailable in some browser contexts.
    }
  }

  const handleClearZerodhaPostbackFailures = async () => {
    setClearingZerodhaPostbackFailures(true)
    try {
      await clearZerodhaPostbackFailures({ include_legacy: true })
      const status = await fetchZerodhaStatus()
      setBrokerStatus(status)
      setZerodhaError(null)
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Failed to clear Zerodha postback failures'
      setZerodhaError(msg)
      recordAppLog('ERROR', msg)
    } finally {
      setClearingZerodhaPostbackFailures(false)
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
            {brokerStatus?.connected && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
                  Order updates (postback)
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Configure the Kite Connect app postback URL to enable automatic refresh after trades.
                </Typography>

                {(() => {
                  const path = brokerStatus?.postback_path || '/api/zerodha/postback'
                  const base = `${window.location.origin}${path}`
                  const withSlash = base.endsWith('/') ? base : `${base}/`
                  const last = brokerStatus?.last_postback_at
                  const lastPretty = last
                    ? formatInTimeZone(last, displayTimeZone === 'LOCAL' ? undefined : displayTimeZone)
                    : null
                  const lastReject = brokerStatus?.last_postback_reject_at
                  const lastRejectPretty = lastReject
                    ? formatInTimeZone(
                        lastReject,
                        displayTimeZone === 'LOCAL' ? undefined : displayTimeZone,
                      )
                    : null
                  const lastNoise = brokerStatus?.last_postback_noise_at
                  const lastNoisePretty = lastNoise
                    ? formatInTimeZone(
                        lastNoise,
                        displayTimeZone === 'LOCAL' ? undefined : displayTimeZone,
                      )
                    : null

                  const rejectDetails = brokerStatus?.last_postback_reject_details
                  const rejectDetailsText =
                    rejectDetails != null ? JSON.stringify(rejectDetails, null, 2) : ''
                  const noiseDetails = brokerStatus?.last_postback_noise_details
                  const noiseDetailsText =
                    noiseDetails != null ? JSON.stringify(noiseDetails, null, 2) : ''

                  return (
                    <>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mb: 1 }}>
                        <TextField
                          size="small"
                          label="Postback URL"
                          value={base}
                          sx={{ flex: 1, minWidth: 340 }}
                          inputProps={{ readOnly: true }}
                        />
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => void handleCopyToClipboard(base)}
                        >
                          Copy
                        </Button>
                      </Box>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mb: 1 }}>
                        <TextField
                          size="small"
                          label="Postback URL (trailing slash)"
                          value={withSlash}
                          sx={{ flex: 1, minWidth: 340 }}
                          inputProps={{ readOnly: true }}
                        />
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => void handleCopyToClipboard(withSlash)}
                        >
                          Copy
                        </Button>
                        <Button
                          variant="outlined"
                          size="small"
                          color="warning"
                          onClick={() => void handleClearZerodhaPostbackFailures()}
                          disabled={clearingZerodhaPostbackFailures}
                        >
                          {clearingZerodhaPostbackFailures ? 'Clearing…' : 'Clear failures'}
                        </Button>
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        {lastPretty ? `Last postback received: ${lastPretty}` : 'Last postback received: (none yet)'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        {lastRejectPretty
                          ? `Last postback rejected: ${lastRejectPretty}`
                          : 'Last postback rejected: (none)'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                        {lastNoisePretty
                          ? `Last postback ignored (missing checksum/signature): ${lastNoisePretty}`
                          : 'Last postback ignored (missing checksum/signature): (none)'}
                      </Typography>

                      {(rejectDetailsText || noiseDetailsText) && (
                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'flex-start', mt: 1 }}>
                          {rejectDetailsText && (
                            <TextField
                              size="small"
                              label="Last rejection details"
                              value={rejectDetailsText}
                              sx={{ flex: 1, minWidth: 340 }}
                              multiline
                              minRows={4}
                              inputProps={{ readOnly: true, style: { fontFamily: 'monospace' } }}
                            />
                          )}
                          {noiseDetailsText && (
                            <TextField
                              size="small"
                              label="Last ignored postback details"
                              value={noiseDetailsText}
                              sx={{ flex: 1, minWidth: 340 }}
                              multiline
                              minRows={4}
                              inputProps={{ readOnly: true, style: { fontFamily: 'monospace' } }}
                            />
                          )}
                        </Box>
                      )}
                    </>
                  )
                })()}
              </Box>
            )}
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
                  label="Default product"
                  value={tvWebhookDefaultProduct}
                  onChange={(e) => setTvWebhookDefaultProduct(e.target.value as 'CNC' | 'MIS')}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="CNC">CNC (Delivery)</MenuItem>
                  <MenuItem value="MIS">MIS (Intraday)</MenuItem>
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
                        default_product: tvWebhookDefaultProduct,
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
          <Box
            sx={{
              display: 'grid',
              gap: 2,
              mb: 3,
              alignItems: 'start',
              gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1fr) 420px' },
            }}
          >
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
              <RiskSettingsBackupPanel />
              <RiskGlobalsPanel />
              <RiskProfilesSettings />
              <RiskSourceOverridesPanel />
              <HoldingsExitAutomationSettings />
            </Box>
            <EffectiveRiskSummaryPanel />
          </Box>
      ) : null}
    </Box>
  )
}
