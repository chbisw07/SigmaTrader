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

function quantile(sorted: number[], q: number): number | null {
  if (!sorted.length) return null
  if (sorted.length === 1) return sorted[0] ?? null
  const qq = Math.min(1, Math.max(0, q))
  const pos = (sorted.length - 1) * qq
  const base = Math.floor(pos)
  const rest = pos - base
  const v0 = sorted[base]
  const v1 = sorted[Math.min(sorted.length - 1, base + 1)]
  if (v0 == null || v1 == null) return null
  return v0 + rest * (v1 - v0)
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
  minQtyPerRow?: number
  optimizeWithRemainingFunds?: boolean
}): AllocationResult {
  const funds = safeNumber(args.funds) ?? 0
  const rows = args.rows ?? []
  const pricesByRowId = args.pricesByRowId ?? {}
  const requireWeightsSumTo100 = args.requireWeightsSumTo100 ?? false
  const minQtyPerRow = Math.max(0, Math.trunc(safeNumber(args.minQtyPerRow) ?? 0))
  const optimizeWithRemainingFunds = args.optimizeWithRemainingFunds ?? true

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

  const baseRows: AllocationRowResult[] = rows.map((r) => {
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

  let outRows = baseRows

  // If minQtyPerRow is requested, compute minimum funds needed so that each row with a non-zero
  // weight can buy at least minQtyPerRow shares at the current weights.
  let minFundsRequired: number | undefined
  if (minQtyPerRow > 0) {
    let maxRequired = 0
    for (const r of outRows) {
      const w = safeNumber(r.weightPct) ?? 0
      const price = safeNumber(r.price)
      if (!(w > 0) || price == null || !(price > 0)) continue
      const required = (price * minQtyPerRow * 100) / w
      if (Number.isFinite(required) && required > maxRequired) maxRequired = required
    }
    if (maxRequired > 0 && Number.isFinite(maxRequired)) {
      minFundsRequired = maxRequired
      const additional = Math.max(0, maxRequired - funds)
      if (additional > 0.01) {
        issues.push({
          level: 'error',
          code: 'min_qty_funds_insufficient',
          message: `Add ${additional.toFixed(2)} funds to buy at least ${minQtyPerRow} share(s) for every included symbol at current weights.`,
        })

        outRows = outRows.map((r) => {
          const w = safeNumber(r.weightPct) ?? 0
          const price = safeNumber(r.price)
          if (!(w > 0) || price == null || !(price > 0)) return r
          const rowTarget = (funds * w) / 100
          if (rowTarget + 1e-9 >= price * minQtyPerRow) return r
          const rowRequired = (price * minQtyPerRow * 100) / w
          return {
            ...r,
            issues: [
              ...r.issues,
              {
                level: 'error',
                code: 'min_qty_unmet',
                message: `Needs at least ${minQtyPerRow} share(s). Minimum funds at current weight: ${rowRequired.toFixed(2)}.`,
                rowId: r.id,
              },
            ],
          }
        })
      }
    }
  }

  // Greedy improvement: spend remaining funds by buying 1 share at a time for the most underweight
  // row (by targetAmount - currentCost), without exceeding available funds.
  if (
    optimizeWithRemainingFunds &&
    !issues.some((i) => i.level === 'error' && i.code === 'min_qty_funds_insufficient')
  ) {
    const candidates = outRows
      .map((r) => {
        const w = safeNumber(r.weightPct) ?? 0
        const price = safeNumber(r.price)
        return { id: r.id, w, price, target: r.targetAmount }
      })
      .filter((c) => c.w > 0 && c.price != null && c.price > 0) as Array<{
      id: string
      w: number
      price: number
      target: number
    }>

    const minPrice = candidates.reduce((m, c) => Math.min(m, c.price), Number.POSITIVE_INFINITY)
    if (candidates.length && Number.isFinite(minPrice)) {
      const qtyById = new Map(outRows.map((r) => [r.id, Math.max(0, Math.trunc(r.plannedQty ?? 0))] as const))
      const costById = new Map(outRows.map((r) => [r.id, Math.max(0, Number(r.plannedCost ?? 0))] as const))
      let totalCost = outRows.reduce((s, r) => s + (Number.isFinite(r.plannedCost) ? r.plannedCost : 0), 0)
      let remaining = funds - totalCost

      // Safety cap: avoid pathological loops when there are penny-priced instruments.
      const maxSteps = 50_000
      let steps = 0
      while (remaining + 1e-9 >= minPrice && steps < maxSteps) {
        steps += 1
        let bestId: string | null = null
        let bestDeficit = 0
        for (const c of candidates) {
          if (c.price > remaining + 1e-9) continue
          const currentCost = costById.get(c.id) ?? 0
          const deficit = c.target - currentCost
          if (deficit > bestDeficit + 1e-9) {
            bestDeficit = deficit
            bestId = c.id
          }
        }
        if (bestId == null) break
        const c = candidates.find((x) => x.id === bestId)
        if (!c) break
        qtyById.set(bestId, (qtyById.get(bestId) ?? 0) + 1)
        costById.set(bestId, (costById.get(bestId) ?? 0) + c.price)
        totalCost += c.price
        remaining -= c.price
      }

      outRows = outRows.map((r) => {
        const qty = qtyById.get(r.id) ?? 0
        const cost = costById.get(r.id) ?? 0
        return { ...r, plannedQty: qty, plannedCost: cost }
      })
    }
  }

  const totalCost = outRows.reduce((s, r) => s + (Number.isFinite(r.plannedCost) ? r.plannedCost : 0), 0)
  const remaining = funds - totalCost

  // Allocation quality: compare invested weights to target weights and detect outliers.
  let maxAbsDeviationPct: number | undefined
  if (totalCost > 0) {
    let maxDev = 0
    const rowDevs: Array<{ id: string; dev: number; symbol: string }> = []
    for (const r of outRows) {
      const w = safeNumber(r.weightPct) ?? 0
      if (!(w > 0)) continue
      const cost = safeNumber(r.plannedCost) ?? 0
      const actual = (cost / totalCost) * 100
      const dev = Math.abs(actual - w)
      if (Number.isFinite(dev)) {
        if (dev > maxDev) maxDev = dev
        rowDevs.push({ id: r.id, dev, symbol: r.symbol })
      }
    }
    if (Number.isFinite(maxDev)) {
      maxAbsDeviationPct = maxDev
      const devVals = rowDevs
        .map((x) => x.dev)
        .filter((x) => Number.isFinite(x))
        .sort((a, b) => a - b)
      const q1 = quantile(devVals, 0.25)
      const q3 = quantile(devVals, 0.75)
      const median = quantile(devVals, 0.5)
      if (q1 != null && q3 != null && median != null) {
        const iqr = q3 - q1
        if (iqr > 1e-9) {
          const upper = median + 2.5 * iqr
          const offenders = rowDevs
            .filter((x) => x.dev > upper + 1e-9)
            .sort((a, b) => b.dev - a.dev)
          if (offenders.length) {
            const top = offenders.slice(0, 3)
            issues.push({
              level: 'warning',
              code: 'allocation_outliers',
              message: `Rounding outliers (weights may skew): ${top
                .map((o) => `${o.symbol} (${o.dev.toFixed(2)}%)`)
                .join(', ')}.`,
            })
            const offenderIds = new Set(offenders.map((o) => o.id))
            outRows = outRows.map((r) => {
              const w = safeNumber(r.weightPct) ?? 0
              const cost = safeNumber(r.plannedCost) ?? 0
              const actual = totalCost > 0 ? (cost / totalCost) * 100 : 0
              const drift = Math.abs(actual - w)
              return {
                ...r,
                actualPct: Number.isFinite(actual) ? actual : null,
                driftPct: Number.isFinite(drift) ? drift : null,
                issues: offenderIds.has(r.id)
                  ? [
                      ...r.issues,
                      {
                        level: 'warning',
                        code: 'allocation_outlier',
                        message:
                          'This symbol is a rounding outlier; consider removing it or increasing funds for a closer match to target weights.',
                        rowId: r.id,
                      },
                    ]
                  : r.issues,
              }
            })
          } else {
            outRows = outRows.map((r) => {
              const w = safeNumber(r.weightPct) ?? 0
              const cost = safeNumber(r.plannedCost) ?? 0
              const actual = totalCost > 0 ? (cost / totalCost) * 100 : 0
              const drift = Math.abs(actual - w)
              return {
                ...r,
                actualPct: Number.isFinite(actual) ? actual : null,
                driftPct: Number.isFinite(drift) ? drift : null,
              }
            })
          }
        } else {
          outRows = outRows.map((r) => {
            const w = safeNumber(r.weightPct) ?? 0
            const cost = safeNumber(r.plannedCost) ?? 0
            const actual = totalCost > 0 ? (cost / totalCost) * 100 : 0
            const drift = Math.abs(actual - w)
            return {
              ...r,
              actualPct: Number.isFinite(actual) ? actual : null,
              driftPct: Number.isFinite(drift) ? drift : null,
            }
          })
        }
      }
    }
  }

  const totals = {
    funds,
    weightSumPct,
    lockedWeightSumPct,
    totalCost,
    remaining,
    minFundsRequired,
    additionalFundsRequired: minFundsRequired != null ? Math.max(0, minFundsRequired - funds) : 0,
    maxAbsDeviationPct,
  }

  // Bubble up row errors.
  for (const r of outRows) {
    for (const i of r.issues) {
      if (i.level === 'error') issues.push(i)
    }
  }

  return { rows: outRows, totals, issues }
}
