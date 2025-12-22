import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import FormControlLabel from '@mui/material/FormControlLabel'
import Checkbox from '@mui/material/Checkbox'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { DataGrid, GridToolbar, type GridCellParams, type GridColDef } from '@mui/x-data-grid'

import {
  fetchDailyPositions,
  syncPositions,
  type PositionSnapshot,
} from '../services/positions'
import { fetchBrokers, type BrokerInfo } from '../services/brokers'

const formatIst = (iso: string): string =>
  new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })

const formatDateLocal = (d: Date): string => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const defaultDateRange = (): { from: string; to: string } => {
  const today = new Date()
  const dayOfWeek = today.getDay() // 0=Sun,1=Mon
  const diffToMonday = (dayOfWeek + 6) % 7
  const monday = new Date(today)
  monday.setDate(today.getDate() - diffToMonday)
  return {
    from: formatDateLocal(monday),
    to: formatDateLocal(today),
  }
}

export function PositionsPage() {
  const defaults = defaultDateRange()
  const [positions, setPositions] = useState<PositionSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [selectedBroker, setSelectedBroker] = useState<string>('zerodha')

  const [startDate, setStartDate] = useState<string>(defaults.from)
  const [endDate, setEndDate] = useState<string>(defaults.to)
  const [symbolQuery, setSymbolQuery] = useState<string>('')
  const [includeZero, setIncludeZero] = useState(true)

  const load = async (opts?: { preferLatest?: boolean }) => {
    try {
      setLoading(true)
      const params =
        opts?.preferLatest && !startDate && !endDate && !symbolQuery
          ? { broker_name: selectedBroker }
          : {
              broker_name: selectedBroker,
              start_date: startDate || undefined,
              end_date: endDate || undefined,
              symbol: symbolQuery || undefined,
              include_zero: includeZero,
            }
      const data = await fetchDailyPositions(params)
      setPositions(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load positions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        const list = await fetchBrokers()
        setBrokers(list)
        if (list.length > 0 && !list.some((b) => b.name === selectedBroker)) {
          setSelectedBroker(list[0].name)
        }
      } catch {
        // Ignore; page can still operate with defaults.
      }
    })()
    void load({ preferLatest: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    // When switching brokers, immediately clear the previous broker's rows so
    // the grid doesn't look "stuck" on the old broker while the request runs.
    setPositions([])
    setError(null)
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBroker])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await syncPositions(selectedBroker)
      await load({ preferLatest: true })
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : `Failed to sync positions from ${selectedBroker}`,
      )
    } finally {
      setRefreshing(false)
    }
  }

  const handleApply = async () => {
    await load()
  }

  const columns: GridColDef[] = [
    { field: 'as_of_date', headerName: 'Date', width: 110 },
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'exchange', headerName: 'Exch', width: 80 },
    { field: 'product', headerName: 'Product', width: 90 },
    { field: 'order_type', headerName: 'Type', width: 90 },
    {
      field: 'traded_qty',
      headerName: 'Qty',
      width: 90,
      type: 'number',
    },
    {
      field: 'remaining_qty',
      headerName: 'Remaining',
      width: 100,
      type: 'number',
    },
    {
      field: 'avg_buy_price',
      headerName: 'Avg Buy',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'avg_sell_price',
      headerName: 'Avg Sell',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'pnl_value',
      headerName: 'P&L',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'pnl_pct',
      headerName: 'P&L %',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? `${Number(v).toFixed(2)}%` : ''),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'ltp',
      headerName: 'LTP',
      width: 100,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'today_pnl',
      headerName: 'Today P&L',
      width: 120,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'today_pnl_pct',
      headerName: 'Today %',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? `${Number(v).toFixed(2)}%` : ''),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'captured_at',
      headerName: 'Captured',
      width: 190,
      valueFormatter: (v) => (v ? formatIst(String(v)) : ''),
    },
  ]

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
          Daily position snapshots (from broker positions). Refresh captures a new snapshot for today.
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          {brokers.length > 0 && (
            <TextField
              select
              label="Broker"
              size="small"
              value={selectedBroker}
              onChange={(e) => setSelectedBroker(e.target.value)}
              sx={{ minWidth: 170 }}
            >
              {brokers.map((b) => (
                <MenuItem key={b.name} value={b.name}>
                  {b.label}
                </MenuItem>
              ))}
            </TextField>
          )}
          <TextField
            label="From"
            type="date"
            size="small"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label="To"
            type="date"
            size="small"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label="Symbol"
            size="small"
            value={symbolQuery}
            onChange={(e) => setSymbolQuery(e.target.value.toUpperCase())}
            sx={{ minWidth: 140 }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={includeZero}
                onChange={(e) => setIncludeZero(e.target.checked)}
              />
            }
            label="Include zero qty"
            sx={{ mr: 0 }}
          />
          <Button
            size="small"
            variant="outlined"
            onClick={handleApply}
            disabled={loading || refreshing}
          >
            Apply
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={handleRefresh}
            disabled={loading || refreshing}
          >
            {refreshing ? 'Refreshing…' : `Refresh from ${selectedBroker}`}
          </Button>
        </Stack>
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
        <Box sx={{ height: 'calc(100vh - 230px)', minHeight: 360 }}>
          <DataGrid
            rows={positions}
            columns={columns}
            getRowId={(r) => r.id}
            density="compact"
            disableRowSelectionOnClick
            sx={{
              '& .pnl-negative': {
                color: 'error.main',
              },
            }}
            slots={{ toolbar: GridToolbar }}
            slotProps={{
              toolbar: {
                showQuickFilter: true,
                quickFilterProps: { debounceMs: 300 },
              },
            }}
            initialState={{
              pagination: { paginationModel: { pageSize: 25 } },
            }}
            pageSizeOptions={[25, 50, 100]}
          />
        </Box>
      )}
    </Box>
  )
}
