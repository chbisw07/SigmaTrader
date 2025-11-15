import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import {
  fetchRiskSettings,
  fetchStrategies,
  type RiskSettings,
  type Strategy,
} from '../services/admin'

export function SettingsPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [riskSettings, setRiskSettings] = useState<RiskSettings[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Read-only view of strategies and risk settings. Editing flows will be added in later
        sprints.
      </Typography>

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
