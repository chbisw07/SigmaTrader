import type { GridRenderCellParams } from '@mui/x-data-grid'

export function getPaginatedRowNumber(params: GridRenderCellParams): number {
  const api = params.api as any

  const paginationModel =
    api?.state?.pagination?.paginationModel ??
    api?.getState?.()?.pagination?.paginationModel ??
    null

  const page = Number(paginationModel?.page ?? 0)
  const pageSize = Number(paginationModel?.pageSize ?? 0)

  const idx = Number(api?.getRowIndexRelativeToVisibleRows?.(params.id) ?? 0)
  if (!Number.isFinite(page) || !Number.isFinite(pageSize) || pageSize <= 0) {
    return idx + 1
  }
  return page * pageSize + idx + 1
}

