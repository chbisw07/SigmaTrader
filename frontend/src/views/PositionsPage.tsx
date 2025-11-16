import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
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
  fetchPositions,
  syncPositions,
  type Position,
} from '../services/positions'

const formatIst = (iso: string): string => {
  const utc = new Date(iso)
  const istMs = utc.getTime() + 5.5 * 60 * 60 * 1000
  const ist = new Date(istMs)
  return ist.toLocaleString('en-IN')
}

export function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = async () => {
    try {
      setLoading(true)
      const data = await fetchPositions()
      setPositions(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load positions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await syncPositions()
      await load()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to sync positions from Zerodha',
      )
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Positions
      </Typography>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 3,
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Typography color="text.secondary">
          Current net positions cached from Zerodha. Use Refresh to update.
        </Typography>
        <Button
          size="small"
          variant="outlined"
          onClick={handleRefresh}
          disabled={loading || refreshing}
        >
          {refreshing ? 'Refreshing…' : 'Refresh from Zerodha'}
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading positions...</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell>Product</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Avg Price</TableCell>
                <TableCell align="right">P&L</TableCell>
                <TableCell>Last Updated</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {positions.map((p) => (
                <TableRow key={`${p.symbol}-${p.product}`}>
                  <TableCell>{p.symbol}</TableCell>
                  <TableCell>{p.product}</TableCell>
                  <TableCell align="right">{p.qty}</TableCell>
                  <TableCell align="right">{p.avg_price.toFixed(2)}</TableCell>
                  <TableCell align="right">{p.pnl.toFixed(2)}</TableCell>
                  <TableCell>{formatIst(p.last_updated)}</TableCell>
                </TableRow>
              ))}
              {positions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography variant="body2" color="text.secondary">
                      No positions currently.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Box>
  )
}

