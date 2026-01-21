export type AllocationRowDraft = {
  id: string
  symbol: string
  exchange?: string | null
  locked: boolean
  weightPct?: number | null
  amountInr?: number | null
  qty?: number | null
}

export type AllocationIssueLevel = 'error' | 'warning'

export type AllocationIssue = {
  level: AllocationIssueLevel
  code: string
  message: string
  rowId?: string
}

export type AllocationRowResult = {
  id: string
  symbol: string
  exchange?: string | null
  locked: boolean
  weightPct: number
  amountInr: number
  qty: number
  price?: number | null
  plannedCost: number
  issues: AllocationIssue[]
  actualPct?: number | null
  driftPct?: number | null
}

export type AllocationTotals = {
  funds: number
  weightSumPct: number
  lockedWeightSumPct: number
  totalCost: number
  remaining: number
  minFundsRequired?: number
  additionalFundsRequired?: number
  maxAbsDeviationPct?: number
}

export type AllocationResult = {
  rows: AllocationRowResult[]
  totals: AllocationTotals
  issues: AllocationIssue[]
}
