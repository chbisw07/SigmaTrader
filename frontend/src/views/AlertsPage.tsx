import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import { useEffect, useState } from 'react'

import {
  listIndicatorRules,
  type IndicatorRule,
} from '../services/indicatorAlerts'
import { listStrategyTemplates, type Strategy } from '../services/strategies'

type RuleRow = IndicatorRule & {
  id: number
  strategy_name?: string | null
}

export function AlertsPage() {
  const [rows, setRows] = useState<RuleRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoading(true)
        setError(null)

        const [rules, templates] = await Promise.all([
          listIndicatorRules(),
          listStrategyTemplates(),
        ])

        if (!active) return

        const byId = new Map<number, Strategy>()
        templates.forEach((tpl) => {
          byId.set(tpl.id, tpl)
        })

        const mapped: RuleRow[] = rules.map((rule) => ({
          ...rule,
          strategy_name:
            rule.strategy_id != null ? byId.get(rule.strategy_id)?.name ?? null : null,
        }))
        setRows(mapped)
      } catch (err) {
        if (!active) return
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load indicator alerts',
        )
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  const columns: GridColDef[] = [
    {
      field: 'symbol',
      headerName: 'Symbol',
      width: 140,
      valueGetter: (_value, row) => row.symbol ?? row.universe ?? '-',
    },
    {
      field: 'strategy_name',
      headerName: 'Strategy',
      width: 220,
      valueFormatter: (v) => v ?? '—',
    },
    {
      field: 'timeframe',
      headerName: 'Timeframe',
      width: 100,
    },
    {
      field: 'action_type',
      headerName: 'Action',
      width: 130,
    },
    {
      field: 'trigger_mode',
      headerName: 'Trigger',
      width: 140,
    },
    {
      field: 'enabled',
      headerName: 'Status',
      width: 120,
      renderCell: (params: GridRenderCellParams<boolean>) => (
        <Chip
          size="small"
          label={params.value ? 'Enabled' : 'Paused'}
          color={params.value ? 'success' : 'default'}
        />
      ),
    },
    {
      field: 'last_triggered_at',
      headerName: 'Last triggered',
      width: 190,
      valueFormatter: (v) => (v ? new Date(v as string).toLocaleString() : '—'),
    },
    {
      field: 'created_at',
      headerName: 'Created at',
      width: 190,
      valueFormatter: (v) => new Date(v as string).toLocaleString(),
    },
  ]

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Alerts
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Indicator-based alert rules created from Holdings, grouped by symbol and
        strategy.
      </Typography>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      <Paper sx={{ height: 520, width: '100%' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          density="compact"
          loading={loading}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          initialState={{
            pagination: { paginationModel: { pageSize: 25 } },
          }}
          pageSizeOptions={[25, 50, 100]}
          localeText={{
            noRowsLabel: loading
              ? 'Loading alerts...'
              : 'No indicator alert rules found.',
          }}
        />
      </Paper>
    </Box>
  )
}

export default AlertsPage

