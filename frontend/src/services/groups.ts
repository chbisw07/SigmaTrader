export type GroupKind =
  | 'WATCHLIST'
  | 'MODEL_PORTFOLIO'
  | 'HOLDINGS_VIEW'
  | 'PORTFOLIO'

export type Group = {
  id: number
  owner_id?: number | null
  name: string
  kind: GroupKind
  description?: string | null
  member_count: number
  funds?: number | null
  allocation_mode?: string | null
  frozen_at?: string | null
  origin_basket_id?: number | null
  bought_at?: string | null
  created_at: string
  updated_at: string
}

export type GroupMember = {
  id: number
  group_id: number
  symbol: string
  exchange?: string | null
  target_weight?: number | null
  reference_qty?: number | null
  reference_price?: number | null
  frozen_price?: number | null
  weight_locked?: boolean
  allocation_amount?: number | null
  allocation_qty?: number | null
  notes?: string | null
  created_at: string
  updated_at: string
}

export type GroupDetail = Group & {
  members: GroupMember[]
}

export type BasketBuyRequest = {
  broker_name?: string | null
  product?: string | null
  order_type?: 'MARKET'
  execution_target?: 'LIVE' | 'PAPER'
  items: Array<{ symbol: string; exchange?: string | null; qty: number }>
}

export type BasketBuyResponse = {
  portfolio_group: GroupDetail
  orders: Array<{ id: number; portfolio_group_id?: number | null }>
  created_at: string
}

export type GroupImportColumnType =
  | 'string'
  | 'number'
  | 'boolean'
  | 'date'
  | 'datetime'

export type GroupImportColumn = {
  key: string
  label: string
  type: GroupImportColumnType
  source_header?: string | null
}

export type GroupImportDataset = {
  id: number
  group_id: number
  source: string
  original_filename?: string | null
  created_at: string
  updated_at: string
  columns: GroupImportColumn[]
  symbol_mapping: Record<string, unknown>
}

export type GroupImportDatasetValuesItem = {
  symbol: string
  exchange: string
  values: Record<string, unknown>
}

export type GroupImportWatchlistResponse = {
  group_id: number
  import_id: number
  imported_members: number
  imported_columns: number
  skipped_symbols: Array<{
    row_index: number
    raw_symbol?: string | null
    raw_exchange?: string | null
    normalized_symbol?: string | null
    normalized_exchange?: string | null
    reason: string
  }>
  skipped_columns: Array<{ header: string; reason: string }>
  warnings: string[]
}

export type PortfolioAllocation = {
  group_id: number
  group_name: string
  symbol: string
  exchange: string
  reference_qty?: number | null
  reference_price?: number | null
}

export type PortfolioAllocationUpdate = {
  group_id: number
  reference_qty: number
}

export async function fetchPortfolioAllocations(params?: {
  symbol?: string
  exchange?: string
}): Promise<PortfolioAllocation[]> {
  const url = new URL('/api/groups/allocations/portfolio', window.location.origin)
  if (params?.symbol) url.searchParams.set('symbol', params.symbol)
  if (params?.exchange) url.searchParams.set('exchange', params.exchange)
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load portfolio allocations (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as PortfolioAllocation[]
}

export async function reconcilePortfolioAllocations(payload: {
  broker_name?: string
  symbol: string
  exchange?: string
  updates: PortfolioAllocationUpdate[]
}): Promise<{
  symbol: string
  exchange: string
  holding_qty: number
  allocated_total: number
  updated_groups: number
}> {
  const res = await fetch('/api/groups/allocations/portfolio/reconcile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to reconcile allocations (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as {
    symbol: string
    exchange: string
    holding_qty: number
    allocated_total: number
    updated_groups: number
  }
}

async function readApiError(res: Response): Promise<string> {
  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    try {
      const data = (await res.json()) as { detail?: unknown }
      if (typeof data.detail === 'string' && data.detail.trim()) return data.detail
      return JSON.stringify(data)
    } catch {
      // fall through
    }
  }

  try {
    const body = await res.text()
    return body.trim()
  } catch {
    return ''
  }
}

export async function listGroups(params?: {
  kind?: GroupKind
}): Promise<Group[]> {
  const url = new URL('/api/groups/', window.location.origin)
  if (params?.kind) url.searchParams.set('kind', params.kind)
  const res = await fetch(url.toString())
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load groups (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as Group[]
}

export async function createGroup(payload: {
  name: string
  kind?: GroupKind
  description?: string | null
}): Promise<Group> {
  const res = await fetch('/api/groups/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to create group (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Group
}

export async function updateGroup(
  groupId: number,
  payload: {
    name?: string
    kind?: GroupKind
    description?: string | null
  },
): Promise<Group> {
  const res = await fetch(`/api/groups/${groupId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to update group (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Group
}

export async function deleteGroup(groupId: number): Promise<void> {
  const res = await fetch(`/api/groups/${groupId}`, { method: 'DELETE' })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to delete group (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
}

export async function fetchGroup(groupId: number): Promise<GroupDetail> {
  const res = await fetch(`/api/groups/${groupId}`)
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load group (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as GroupDetail
}

export async function importWatchlistCsv(payload: {
  group_name: string
  group_kind?: 'WATCHLIST' | 'MODEL_PORTFOLIO' | 'PORTFOLIO'
  group_description?: string | null
  source?: string
  original_filename?: string | null
  symbol_column: string
  exchange_column?: string | null
  default_exchange?: string
  reference_qty_column?: string | null
  reference_price_column?: string | null
  target_weight_column?: string | null
  target_weight_units?: 'AUTO' | 'PCT' | 'FRACTION'
  selected_columns: string[]
  header_labels?: Record<string, string>
  rows: Array<Record<string, unknown>>
  strip_exchange_prefix?: boolean
  strip_special_chars?: boolean
  allow_kite_fallback?: boolean
  conflict_mode?: 'ERROR' | 'REPLACE_DATASET' | 'REPLACE_GROUP'
  replace_members?: boolean
}): Promise<GroupImportWatchlistResponse> {
  const res = await fetch('/api/groups/import/watchlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to import watchlist (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as GroupImportWatchlistResponse
}

export async function fetchGroupDataset(
  groupId: number,
): Promise<GroupImportDataset | null> {
  const res = await fetch(`/api/groups/${groupId}/dataset`)
  if (res.status === 404) return null
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load group dataset (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as GroupImportDataset
}

export async function fetchGroupDatasetValues(
  groupId: number,
): Promise<GroupImportDatasetValuesItem[]> {
  const res = await fetch(`/api/groups/${groupId}/dataset/values`)
  if (res.status === 404) return []
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load group dataset values (${res.status})${
        detail ? `: ${detail}` : ''
      }`,
    )
  }
  const data = (await res.json()) as { items?: GroupImportDatasetValuesItem[] }
  return Array.isArray(data.items) ? data.items : []
}

export async function listGroupMembers(groupId: number): Promise<GroupMember[]> {
  const res = await fetch(`/api/groups/${groupId}/members`)
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load group members (${res.status})${
        detail ? `: ${detail}` : ''
      }`,
    )
  }
  return (await res.json()) as GroupMember[]
}

export async function addGroupMember(
  groupId: number,
  payload: {
    symbol: string
    exchange?: string | null
    target_weight?: number | null
    reference_qty?: number | null
    reference_price?: number | null
    notes?: string | null
  },
): Promise<GroupMember> {
  const res = await fetch(`/api/groups/${groupId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to add member (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as GroupMember
}

export async function bulkAddGroupMembers(
  groupId: number,
  payload: Array<{
    symbol: string
    exchange?: string | null
    target_weight?: number | null
    reference_qty?: number | null
    reference_price?: number | null
    notes?: string | null
  }>,
): Promise<GroupMember[]> {
  const res = await fetch(`/api/groups/${groupId}/members/bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to add members (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as GroupMember[]
}

export type WatchlistBulkAddSafeResponse = {
  added: number
  skipped: Array<{
    raw: string
    normalized_symbol?: string | null
    normalized_exchange?: string | null
    reason: string
  }>
}

export async function bulkAddWatchlistMembersSafe(
  groupId: number,
  payload: { items: string[]; default_exchange?: string },
): Promise<WatchlistBulkAddSafeResponse> {
  const res = await fetch(`/api/groups/${groupId}/members/bulk-add-safe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to bulk add watchlist members (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as WatchlistBulkAddSafeResponse
}

export async function updateGroupMember(
  groupId: number,
  memberId: number,
  payload: {
    target_weight?: number | null
    reference_qty?: number | null
    reference_price?: number | null
    weight_locked?: boolean | null
    allocation_amount?: number | null
    allocation_qty?: number | null
    notes?: string | null
  },
): Promise<GroupMember> {
  const res = await fetch(`/api/groups/${groupId}/members/${memberId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to update member (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as GroupMember
}

export async function updateBasketConfig(
  groupId: number,
  payload: { funds?: number | null; allocation_mode?: 'WEIGHT' | 'AMOUNT' | 'QTY' | null },
): Promise<Group> {
  const res = await fetch(`/api/groups/${groupId}/basket/config`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to update basket config (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Group
}

export async function freezeBasket(groupId: number): Promise<GroupDetail> {
  const res = await fetch(`/api/groups/${groupId}/basket/freeze`, {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to freeze basket prices (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as GroupDetail
}

export async function buyBasketToPortfolio(
  basketGroupId: number,
  payload: BasketBuyRequest,
): Promise<BasketBuyResponse> {
  const res = await fetch(`/api/groups/${basketGroupId}/buy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to buy basket (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as BasketBuyResponse
}

export async function deleteGroupMember(
  groupId: number,
  memberId: number,
): Promise<void> {
  const res = await fetch(`/api/groups/${groupId}/members/${memberId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const body = await readApiError(res)
    throw new Error(
      `Failed to delete member (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
}

export async function fetchGroupMemberships(
  symbols: string[],
): Promise<Record<string, string[]>> {
  const chunkSize = 50
  const chunks: string[][] = []
  for (let i = 0; i < symbols.length; i += chunkSize) {
    chunks.push(symbols.slice(i, i + chunkSize))
  }

  const responses = await Promise.all(
    chunks.map(async (chunk) => {
      const url = new URL('/api/groups/memberships/by-symbol', window.location.origin)
      for (const symbol of chunk) {
        url.searchParams.append('symbols', symbol)
      }
      const res = await fetch(url.toString())
      if (!res.ok) {
        const detail = await readApiError(res)
        throw new Error(
          `Failed to load group memberships (${res.status})${
            detail ? `: ${detail}` : ''
          }`,
        )
      }
      const data = (await res.json()) as {
        memberships: Record<string, string[]>
      }
      return data.memberships ?? {}
    }),
  )

  const merged: Record<string, string[]> = {}
  for (const res of responses) {
    for (const [symbol, groups] of Object.entries(res)) {
      if (!merged[symbol]) merged[symbol] = []
      merged[symbol] = [...merged[symbol], ...groups]
    }
  }

  for (const [symbol, groups] of Object.entries(merged)) {
    merged[symbol] = Array.from(new Set(groups)).sort()
  }

  return merged
}
