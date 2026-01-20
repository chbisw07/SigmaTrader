import DeleteIcon from '@mui/icons-material/Delete'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'
import { useMemo } from 'react'

import { getPaginatedRowNumber } from '../UniverseGrid/getPaginatedRowNumber'
import type { MarketQuote } from '../../services/marketQuotes'
import type { GroupMember } from '../../services/groups'

export type WatchlistMembersGridProps = {
  members: GroupMember[]
  quotesByKey: Record<string, MarketQuote>
  onRemove: (member: GroupMember) => void
  loading?: boolean
}

export function WatchlistMembersGrid({
  members,
  quotesByKey,
  onRemove,
  loading = false,
}: WatchlistMembersGridProps) {
  const columns = useMemo((): GridColDef<GroupMember>[] => {
    const cols: GridColDef<GroupMember>[] = [
      {
        field: 'index',
        headerName: '#',
        width: 70,
        sortable: false,
        filterable: false,
        renderCell: (params: GridRenderCellParams<GroupMember>) =>
          getPaginatedRowNumber(params),
      },
      { field: 'symbol', headerName: 'Symbol', width: 160 },
      {
        field: 'exchange',
        headerName: 'Exchange',
        width: 110,
        valueGetter: (_v, row) => row.exchange ?? 'NSE',
      },
      {
        field: 'ltp',
        headerName: 'LTP',
        width: 110,
        valueGetter: (_v, row) => {
          const sym = (row.symbol || '').trim().toUpperCase()
          const exch = (row.exchange || 'NSE').trim().toUpperCase()
          const q = quotesByKey[`${exch}:${sym}`]
          return q?.ltp ?? null
        },
        valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '—'),
      },
      {
        field: 'day_pct',
        headerName: 'Day %',
        width: 110,
        valueGetter: (_v, row) => {
          const sym = (row.symbol || '').trim().toUpperCase()
          const exch = (row.exchange || 'NSE').trim().toUpperCase()
          const q = quotesByKey[`${exch}:${sym}`]
          return q?.day_pct ?? null
        },
        valueFormatter: (v) =>
          v != null && Number.isFinite(Number(v)) ? `${Number(v).toFixed(2)}%` : '—',
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 160,
        sortable: false,
        filterable: false,
        renderCell: (params: GridRenderCellParams<GroupMember>) => (
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={() => onRemove(params.row)}
            >
              Remove
            </Button>
          </Stack>
        ),
      },
    ]
    return cols
  }, [onRemove, quotesByKey])

  return (
    <DataGrid
      rows={members}
      columns={columns}
      loading={loading}
      getRowId={(row) => row.id}
      disableRowSelectionOnClick
      pageSizeOptions={[10, 25, 50]}
      initialState={{ pagination: { paginationModel: { pageSize: 25, page: 0 } } }}
    />
  )
}

