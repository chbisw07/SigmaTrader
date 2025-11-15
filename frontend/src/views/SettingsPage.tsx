import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import MenuItem from '@mui/material/MenuItem'
import { useEffect, useState } from 'react'

import {
  fetchRiskSettings,
  fetchStrategies,
  createRiskSettings,
  updateStrategyExecutionMode,
  type RiskSettings,
  type Strategy,
} from '../services/admin'

import {
  connectZerodha,
  fetchZerodhaLoginUrl,
  fetchZerodhaStatus,
  type ZerodhaStatus,
} from '../services/zerodha'

export function SettingsPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [riskSettings, setRiskSettings] = useState<RiskSettings[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [brokerStatus, setBrokerStatus] = useState<ZerodhaStatus | null>(null)
  const [brokerError, setBrokerError] = useState<string | null>(null)
  const [requestToken, setRequestToken] = useState('')
  const [isConnecting, setIsConnecting] = useState(false)
  const [updatingStrategyId, setUpdatingStrategyId] = useState<number | null>(null)
  const [savingRisk, setSavingRisk] = useState(false)
  const [riskScope, setRiskScope] = useState<'GLOBAL' | 'STRATEGY'>('GLOBAL')
  const [riskStrategyId, setRiskStrategyId] = useState<string>('')
  const [riskMaxOrderValue, setRiskMaxOrderValue] = useState<string>('')
  const [riskMaxQty, setRiskMaxQty] = useState<string>('')
  const [riskMaxDailyLoss, setRiskMaxDailyLoss] = useState<string>('')
  const [riskClampMode, setRiskClampMode] = useState<'CLAMP' | 'REJECT'>('CLAMP')
  const [riskShortSelling, setRiskShortSelling] = useState<'ALLOWED' | 'DISABLED'>(
    'ALLOWED',
  )

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
        const status = await fetchZerodhaStatus()
        if (!active) return
        setBrokerStatus(status)
        setBrokerError(null)
      } catch (err) {
        if (!active) return
        setBrokerError(
          err instanceof Error ? err.message : 'Failed to load Zerodha status',
        )
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
      setBrokerError(
        err instanceof Error ? err.message : 'Failed to open Zerodha login',
      )
    }
  }

  const handleConnectZerodha = async () => {
    if (!requestToken.trim()) {
      setBrokerError('Please paste the request_token from Zerodha.')
      return
    }
    setIsConnecting(true)
    try {
      await connectZerodha(requestToken.trim())
      const status = await fetchZerodhaStatus()
      setBrokerStatus(status)
      setBrokerError(null)
    } catch (err) {
      setBrokerError(
        err instanceof Error ? err.message : 'Failed to complete Zerodha connect',
      )
    } finally {
      setIsConnecting(false)
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

  const handleSaveRiskSettings = async () => {
    try {
      if (riskScope === 'STRATEGY' && !riskStrategyId) {
        setError('Please select a strategy for STRATEGY scope risk settings.')
        return
      }

      const payload: any = {
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

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Manage strategies, risk settings, and Zerodha connection details.
      </Typography>

      <Paper sx={{ mb: 3, p: 2 }}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', md: 'row' },
            gap: 2,
            alignItems: { xs: 'flex-start', md: 'center' },
            justifyContent: 'space-between',
          }}
        >
          <Box>
            <Typography variant="h6" gutterBottom>
              Zerodha Connection
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Use the button below to open the Zerodha login page. After completing login,
              paste the <code>request_token</code> here and click Connect.
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button
                variant="outlined"
                size="small"
                onClick={handleOpenZerodhaLogin}
              >
                Open Zerodha Login
              </Button>
              <Chip
                size="small"
                label={
                  brokerStatus?.connected ? 'Zerodha: Connected' : 'Zerodha: Not connected'
                }
                color={brokerStatus?.connected ? 'success' : 'default'}
              />
            </Box>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <TextField
                size="small"
                label="request_token"
                value={requestToken}
                onChange={(e) => setRequestToken(e.target.value)}
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
            {brokerStatus?.updated_at && (
              <Typography variant="caption" color="text.secondary">
                Last updated{' '}
                {(() => {
                  const utc = new Date(brokerStatus.updated_at)
                  const istMs = utc.getTime() + 5.5 * 60 * 60 * 1000
                  const ist = new Date(istMs)
                  return ist.toLocaleString('en-IN')
                })()}
              </Typography>
            )}
            {brokerStatus?.connected && brokerStatus.user_id && (
              <Typography variant="caption" color="text.secondary">
                Zerodha user: {brokerStatus.user_name ?? brokerStatus.user_id}
              </Typography>
            )}
            {brokerError && (
              <Typography variant="caption" color="error">
                {brokerError}
              </Typography>
            )}
          </Box>
        </Box>
      </Paper>

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading strategies and risk settings...</Typography>
        </Box>
      ) : error ? (
        <Typography color="error" variant="body2">
          {error}
        </Typography>
      ) : (
        <>
          <Paper sx={{ mb: 3, p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Strategies
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Mode</TableCell>
                  <TableCell>Enabled</TableCell>
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
                    <TableCell>{strategy.enabled ? 'Yes' : 'No'}</TableCell>
                    <TableCell>{strategy.description}</TableCell>
                  </TableRow>
                ))}
                {strategies.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography variant="body2" color="text.secondary">
                        No strategies configured yet.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>

          <Paper sx={{ p: 2 }}>
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
                  </TableRow>
                ))}
                {riskSettings.length === 0 && (
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
        </>
      )}
    </Box>
  )
}
