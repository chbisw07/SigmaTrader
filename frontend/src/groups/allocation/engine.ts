import type {
  AllocationIssue,
  AllocationResult,
  AllocationRowDraft,
  AllocationRowResult,
} from './types'

const PCT_EPS = 1e-6

function roundTo(value: number, decimals: number): number {
  if (!Number.isFinite(value)) return 0
  const p = 10 ** decimals
  return Math.round(value * p) / p
}

function safeNumber(value: unknown): number | null {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function sumWeightPct(rows: AllocationRowDraft[]): number {
  return rows.reduce((s, r) => s + (Number.isFinite(r.weightPct) ? r.weightPct : 0), 0)
}

export function sumLockedWeightPct(rows: AllocationRowDraft[]): number {
  return rows.reduce((s, r) => s + (r.locked ? (Number.isFinite(r.weightPct) ? r.weightPct : 0) : 0), 0)
}

export function clearUnlocked(rows: AllocationRowDraft[]): AllocationRowDraft[] {
  return rows.map((r) => (r.locked ? r : { ...r, weightPct: 0 }))
}

export function equalizeUnlocked(
  rows: AllocationRowDraft[],
  opts?: { decimals?: number },
): AllocationRowDraft[] {
  const decimals = opts?.decimals ?? 2
  const lockedSum = sumLockedWeightPct(rows)
  const unlocked = rows.filter((r) => !r.locked)
  if (!unlocked.length) return rows

  const remaining = Math.max(0, 100 - lockedSum)
  const base = remaining / unlocked.length
  const roundedBase = roundTo(base, decimals)

  let acc = 0
  const out = rows.map((r) => {
    if (r.locked) return r
    acc += roundedBase
    return { ...r, weightPct: roundedBase }
  })

  // Fix rounding drift on the last unlocked row so weights sum exactly to locked+remaining.
  const unlockedIds = out.filter((r) => !r.locked).map((r) => r.id)
  const lastId = unlockedIds[unlockedIds.length - 1]
  const currentSum = sumWeightPct(out)
  const targetSum = lockedSum + remaining
  const drift = roundTo(targetSum - currentSum, decimals)
  if (lastId != null && Math.abs(drift) > PCT_EPS) {
    return out.map((r) =>
      r.id === lastId ? { ...r, weightPct: roundTo(r.weightPct + drift, decimals) } : r,
    )
  }
  return out
}

export function normalizeUnlocked(
  rows: AllocationRowDraft[],
  opts?: { decimals?: number },
): AllocationRowDraft[] {
  const decimals = opts?.decimals ?? 2
  const lockedSum = sumLockedWeightPct(rows)
  const remaining = Math.max(0, 100 - lockedSum)
  const unlocked = rows.filter((r) => !r.locked)
  if (!unlocked.length) return rows

  const unlockedSum = unlocked.reduce((s, r) => s + (Number.isFinite(r.weightPct) ? r.weightPct : 0), 0)
  if (unlockedSum <= PCT_EPS) {
    return equalizeUnlocked(rows, { decimals })
  }

  const scale = remaining / unlockedSum
  const scaled = rows.map((r) =>
    r.locked ? r : { ...r, weightPct: roundTo(r.weightPct * scale, decimals) },
  )

  // Fix rounding drift on the last unlocked row.
  const unlockedIds = scaled.filter((r) => !r.locked).map((r) => r.id)
  const lastId = unlockedIds[unlockedIds.length - 1]
  const currentSum = sumWeightPct(scaled)
  const targetSum = lockedSum + remaining
  const drift = roundTo(targetSum - currentSum, decimals)
  if (lastId != null && Math.abs(drift) > PCT_EPS) {
    return scaled.map((r) =>
      r.id === lastId ? { ...r, weightPct: roundTo(r.weightPct + drift, decimals) } : r,
    )
  }
  return scaled
}

export function computeWeightModeAllocation(args: {
  funds: number
  rows: AllocationRowDraft[]
  pricesByRowId: Record<string, number | null | undefined>
  requireWeightsSumTo100?: boolean
}): AllocationResult {
  const funds = safeNumber(args.funds) ?? 0
  const rows = args.rows ?? []
  const pricesByRowId = args.pricesByRowId ?? {}
  const requireWeightsSumTo100 = args.requireWeightsSumTo100 ?? false

  const issues: AllocationIssue[] = []
  if (!(funds > 0)) {
    issues.push({
      level: 'error',
      code: 'funds_invalid',
      message: 'Funds must be a positive number.',
    })
  }

  const lockedWeightSumPct = sumLockedWeightPct(rows)
  const weightSumPct = sumWeightPct(rows)
  if (lockedWeightSumPct > 100 + PCT_EPS) {
    issues.push({
      level: 'error',
      code: 'locked_over_100',
      message: 'Locked weights exceed 100%.',
    })
  }
  if (requireWeightsSumTo100 && Math.abs(weightSumPct - 100) > 0.01) {
    issues.push({
      level: 'error',
      code: 'weights_not_100',
      message: 'Weights must sum to 100% to save.',
    })
  }

  const outRows: AllocationRowResult[] = rows.map((r) => {
    const rowIssues: AllocationIssue[] = []
    const w = safeNumber(r.weightPct) ?? 0
    if (!(w >= 0) || w > 100 + PCT_EPS) {
      rowIssues.push({
        level: 'error',
        code: 'weight_invalid',
        message: 'Weight must be between 0 and 100.',
        rowId: r.id,
      })
    }

    const priceRaw = pricesByRowId[r.id]
    const price = safeNumber(priceRaw)
    const targetAmount = funds > 0 && w > 0 ? (funds * w) / 100 : 0
    let plannedQty = 0
    let plannedCost = 0
    if (w > 0) {
      if (price == null || !(price > 0)) {
        rowIssues.push({
          level: 'error',
          code: 'price_missing',
          message: 'Missing price for allocation.',
          rowId: r.id,
        })
      } else {
        plannedQty = Math.floor(targetAmount / price)
        plannedCost = plannedQty * price
        if (plannedQty <= 0) {
          rowIssues.push({
            level: 'warning',
            code: 'qty_zero',
            message: 'Allocated amount is too small for 1 share.',
            rowId: r.id,
          })
        }
      }
    }

    return {
      ...r,
      price,
      targetAmount,
      plannedQty,
      plannedCost,
      issues: rowIssues,
    }
  })

  const totalCost = outRows.reduce((s, r) => s + (Number.isFinite(r.plannedCost) ? r.plannedCost : 0), 0)
  const remaining = funds - totalCost
  const totals = {
    funds,
    weightSumPct,
    lockedWeightSumPct,
    totalCost,
    remaining,
  }

  // Bubble up row errors.
  for (const r of outRows) {
    for (const i of r.issues) {
      if (i.level === 'error') issues.push(i)
    }
  }

  return { rows: outRows, totals, issues }
}

