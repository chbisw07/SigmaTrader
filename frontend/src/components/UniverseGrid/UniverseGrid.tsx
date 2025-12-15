import Paper from '@mui/material/Paper'
import {
  DataGrid,
  GridToolbar,
  GridLogicOperator,
  type GridColDef,
  type GridColumnVisibilityModel,
  type GridRowSelectionModel,
  type GridValidRowModel,
  type DataGridProps,
} from '@mui/x-data-grid'

type UniverseGridProps<RowT extends GridValidRowModel> = {
  rows: RowT[]
  columns: GridColDef[]
  getRowId: DataGridProps<RowT>['getRowId']
  rowSelectionModel: GridRowSelectionModel
  onRowSelectionModelChange: (next: GridRowSelectionModel) => void
  columnVisibilityModel: GridColumnVisibilityModel
  onColumnVisibilityModelChange: (next: GridColumnVisibilityModel) => void
  height?: number | string
  density?: DataGridProps<RowT>['density']
  disableRowSelectionOnClick?: boolean
  checkboxSelection?: boolean
  sx?: DataGridProps<RowT>['sx']
  slots?: DataGridProps<RowT>['slots']
  slotProps?: DataGridProps<RowT>['slotProps']
  initialState?: DataGridProps<RowT>['initialState']
  pageSizeOptions?: DataGridProps<RowT>['pageSizeOptions']
  localeText?: DataGridProps<RowT>['localeText']
}

export function UniverseGrid<RowT extends GridValidRowModel>(
  props: UniverseGridProps<RowT>,
) {
  const {
    rows,
    columns,
    getRowId,
    rowSelectionModel,
    onRowSelectionModelChange,
    columnVisibilityModel,
    onColumnVisibilityModelChange,
    height = '70vh',
    density = 'compact',
    disableRowSelectionOnClick = true,
    checkboxSelection = true,
    sx,
    slots,
    slotProps,
    initialState,
    pageSizeOptions,
    localeText,
  } = props

  return (
    <Paper sx={{ mt: 1, height, width: '100%' }}>
      <DataGrid
        rows={rows}
        columns={columns}
        getRowId={getRowId}
        checkboxSelection={checkboxSelection}
        rowSelectionModel={rowSelectionModel}
        onRowSelectionModelChange={onRowSelectionModelChange}
        density={density}
        columnVisibilityModel={columnVisibilityModel}
        onColumnVisibilityModelChange={onColumnVisibilityModelChange}
        disableRowSelectionOnClick={disableRowSelectionOnClick}
        sx={{ height: '100%', ...sx }}
        slots={slots ?? { toolbar: GridToolbar }}
        slotProps={{
          toolbar: {
            showQuickFilter: true,
            quickFilterProps: { debounceMs: 300 },
          },
          filterPanel: {
            logicOperators: [GridLogicOperator.And],
          },
          ...slotProps,
        }}
        initialState={
          initialState ?? { pagination: { paginationModel: { pageSize: 25 } } }
        }
        pageSizeOptions={pageSizeOptions ?? [25, 50, 100]}
        localeText={localeText ?? { noRowsLabel: 'No rows found.' }}
      />
    </Paper>
  )
}

