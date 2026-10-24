// Groups markets into a "round" (same asset + timeframe + close time) so users see one strike ladder.
import type { Market } from './types'

export interface Round {
  closesAt: string
  strikes: Market[] // sorted by target price, ascending
}

export function roundsFor(markets: Market[], symbol: string, duration: number): Round[] {
  const map = new Map<string, Market[]>()
  for (const m of markets) {
    if (m.symbol !== symbol || m.duration_seconds !== duration) continue
    const list = map.get(m.closes_at) ?? []
    list.push(m)
    map.set(m.closes_at, list)
  }
  return [...map.entries()]
    .sort(([a], [b]) => Date.parse(a) - Date.parse(b))
    .map(([closesAt, list]) => ({
      closesAt,
      strikes: [...list].sort((a, b) => Number(a.target_price) - Number(b.target_price)),
    }))
}

/** The strike closest to the last price (ties go to the lower one). */
export function nearestStrike(strikes: Market[], last: string | null): Market | undefined {
  if (strikes.length === 0) return undefined
  const ref = Number(last)
  if (!Number.isFinite(ref) || ref <= 0) return strikes[Math.floor(strikes.length / 2)]
  return strikes.reduce((best, m) =>
    Math.abs(Number(m.target_price) - ref) < Math.abs(Number(best.target_price) - ref) ? m : best,
  )
}

/** How far a strike is from the last price, e.g. "+2.0%" (null when unknown). */
export function distancePct(target: string, last: string | null): string | null {
  const t = Number(target)
  const l = Number(last)
  if (!(t > 0) || !(l > 0)) return null
  const pct = ((t - l) / l) * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
}
