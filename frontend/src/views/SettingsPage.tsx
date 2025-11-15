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
import { useEffect, useState } from 'react'

import {
  fetchRiskSettings,
  fetchStrategies,
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

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Read-only view of strategies and risk settings. Editing flows will be added in later
        sprints.
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
                    <TableCell>{strategy.execution_mode}</TableCell>
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
