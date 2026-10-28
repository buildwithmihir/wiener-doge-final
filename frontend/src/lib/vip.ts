import type { VipResponse, VipTier } from './types'

/** Progress (0-100, integer) toward the next tier, from base units. BigInt only; never exceeds 100. */
export function progressPct(v: Pick<VipResponse, 'total_staked' | 'current' | 'next'>): number {
  if (!v.next) return 100
  const floor = v.current ? BigInt(v.current.min_staked.units) : 0n
  const ceil = BigInt(v.next.min_staked.units)
  const span = ceil - floor
  if (span <= 0n) return 100
  const done = BigInt(v.total_staked.units) - floor
  if (done <= 0n) return 0
  const pct = Number((done * 100n) / span)
  return Math.min(100, pct)
}

/** % of a tier's threshold already staked (250 of 500 => 50). Never exceeds 100. */
export function tierPct(totalUnits: string, tier: VipTier): number {
  const need = BigInt(tier.min_staked.units)
  if (need <= 0n) return 100
  return Math.min(100, Number((BigInt(totalUnits) * 100n) / need))
}