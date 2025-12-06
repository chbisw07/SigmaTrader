import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import { DataGrid, GridToolbar, type GridColDef } from '@mui/x-data-grid'
import { useEffect, useState } from 'react'

import { fetchHoldings, type Holding } from '../services/positions'

export function HoldingsPage() {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const data = await fetchHoldings()
      setHoldings(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load holdings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const columns: GridColDef[] = [
    {
      field: 'symbol',
      headerName: 'Symbol',
      flex: 1,
      minWidth: 140,
    },
    {
      field: 'quantity',
      headerName: 'Qty',
      type: 'number',
      width: 100,
    },
    {
      field: 'average_price',
      headerName: 'Avg Price',
      type: 'number',
      width: 130,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'last_price',
      headerName: 'Last Price',
      type: 'number',
      width: 130,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'pnl',
      headerName: 'Unrealized P&L',
      type: 'number',
      width: 150,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
  ]

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Holdings
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Live holdings fetched from Zerodha, including unrealized P&amp;L when last
        price is available.
      </Typography>

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading holdings...</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Paper sx={{ mt: 1, height: 600, width: '100%' }}>
          <DataGrid
            rows={holdings}
            columns={columns}
            getRowId={(row) => row.symbol}
            density="compact"
            disableRowSelectionOnClick
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
            localeText={{
              noRowsLabel: 'No holdings found.',
            }}
          />
        </Paper>
      )}
    </Box>
  )
}
