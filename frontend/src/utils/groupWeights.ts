export type MemberWithTargetWeight = {
  symbol: string
  exchange?: string | null
  target_weight?: number | null
}

function keyOf(exchange: string | null | undefined, symbol: string | null | undefined): string {
  const sym = (symbol || '').trim().toUpperCase()
  const exch = (exchange || 'NSE').trim().toUpperCase() || 'NSE'
  return `${exch}:${sym}`
}

export function normalizeTargetWeights(members: MemberWithTargetWeight[]): Record<string, number> {
  if (!members.length) return {}

  const allUnspecified = members.every((m) => m.target_weight == null)
  if (allUnspecified) {
    const eq = 1 / members.length
    const out: Record<string, number> = {}
    for (const m of members) out[keyOf(m.exchange, m.symbol)] = eq
    return out
  }

  const unspecifiedIdx: number[] = []
  let specifiedSum = 0
  for (let idx = 0; idx < members.length; idx++) {
    const wRaw = members[idx]?.target_weight
    if (wRaw == null) {
      unspecifiedIdx.push(idx)
      continue
    }
    const w = Number(wRaw)
    if (!Number.isFinite(w) || w <= 0) continue
    specifiedSum += w
  }

  const weights: number[] = []
  if (specifiedSum <= 0) {
    const eq = 1 / members.length
    for (let i = 0; i < members.length; i++) weights.push(eq)
  } else if (specifiedSum >= 1) {
    for (const m of members) {
      const w = Math.max(0, Number(m.target_weight ?? 0))
      weights.push(specifiedSum > 0 ? w / specifiedSum : 0)
    }
  } else {
    const leftover = 1 - specifiedSum
    const perUnspecified = unspecifiedIdx.length ? leftover / unspecifiedIdx.length : 0
    for (const m of members) {
      if (m.target_weight == null) {
        weights.push(perUnspecified)
      } else {
        weights.push(Math.max(0, Number(m.target_weight)))
      }
    }
    const total = weights.reduce((a, b) => a + b, 0)
    if (total > 0) {
      for (let i = 0; i < weights.length; i++) weights[i] = weights[i] / total
    }
  }

  const out: Record<string, number> = {}
  for (let i = 0; i < members.length; i++) {
    out[keyOf(members[i].exchange, members[i].symbol)] = Number(weights[i] ?? 0)
  }
  return out
}

export type MemberWithoutWeight = {
  symbol: string
  exchange?: string | null
}

export type HoldingSnapshot = {
  qty: number
  avgPrice: number | null
  lastPrice: number | null
}

export function computeHoldingsWeights(
  members: MemberWithoutWeight[],
  resolveHolding: (
    exchange: string | null | undefined,
    symbol: string | null | undefined,
  ) => HoldingSnapshot | null,
): Record<string, number> {
  if (!members.length) return {}

  const values: number[] = []
  const qtys: number[] = []
  for (const m of members) {
    const hold = resolveHolding(m.exchange, m.symbol)
    const qty = Number(hold?.qty ?? 0)
    qtys.push(Number.isFinite(qty) ? qty : 0)

    const last = Number(hold?.lastPrice ?? 0)
    const avg = Number(hold?.avgPrice ?? 0)
    const price =
      Number.isFinite(last) && last > 0 ? last : Number.isFinite(avg) && avg > 0 ? avg : 0
    values.push((Number.isFinite(qty) && qty > 0 ? qty : 0) * price)
  }

  const totalValue = values.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0)
  if (totalValue > 0) {
    const out: Record<string, number> = {}
    for (let i = 0; i < members.length; i++) {
      out[keyOf(members[i].exchange, members[i].symbol)] = (values[i] ?? 0) / totalValue
    }
    return out
  }

  const totalQty = qtys.reduce((a, b) => a + (Number.isFinite(b) && b > 0 ? b : 0), 0)
  if (totalQty > 0) {
    const out: Record<string, number> = {}
    for (let i = 0; i < members.length; i++) {
      const q = Number.isFinite(qtys[i] ?? 0) && (qtys[i] ?? 0) > 0 ? (qtys[i] ?? 0) : 0
      out[keyOf(members[i].exchange, members[i].symbol)] = q / totalQty
    }
    return out
  }

  const eq = 1 / members.length
  const out: Record<string, number> = {}
  for (const m of members) out[keyOf(m.exchange, m.symbol)] = eq
  return out
}

