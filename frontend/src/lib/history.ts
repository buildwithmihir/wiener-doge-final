import type { Prediction } from './types'
import { unitsToDemo } from './money'

export type HistoryFilter = 'all' | 'open' | 'won' | 'lost' | 'refunded' | 'cashed_out'

export const FILTERS: { key: HistoryFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'open', label: 'Live bets' },
  { key: 'won', label: 'Won' },
  { key: 'lost', label: 'Lost' },
  { key: 'cashed_out', label: 'Cashed out' },
  { key: 'refunded', label: 'Refunded' },
]

export interface Summary {
  settled: number
  wins: number
  winRatePct: string // "62.5" or "—"
  netDemo: string // signed, e.g. "+12.5" / "-3"
}

/**
 * Net result of finished predictions: won -> payout - stake, lost -> -stake,
 * cashed out -> payout - stake (counts for profit, NOT for "settled" / win rate), refunded -> 0. BigInt only.
 */
export function summarize(items: Prediction[]): Summary {
  let wins = 0
  let losses = 0
  let net = 0n
  for (const p of items) {
    const stake = BigInt(p.stake.units)
    if (p.status === 'won') {
      wins += 1
      net += BigInt(p.payout.units) - stake
    } else if (p.status === 'lost') {
      losses += 1
      net -= stake
    } else if (p.status === 'cashed_out') {
      net += BigInt(p.payout.units) - stake
    }
  }
  const settled = wins + losses
  const winRatePct = settled === 0 ? '—' : (Math.round((wins * 1000) / settled) / 10).toString()
  const abs = net < 0n ? -net : net
  const body = unitsToDemo(abs)
  const netDemo = net === 0n ? '0' : `${net < 0n ? '-' : '+'}${body}`
  return { settled, wins, winRatePct, netDemo }
}