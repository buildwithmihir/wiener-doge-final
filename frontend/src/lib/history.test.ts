import { describe, expect, it } from 'vitest'
import { summarize } from './history'
import type { Prediction } from './types'

const m = (units: string) => ({ units, demo: '' })
const p = (status: Prediction['status'], stake: string, payout: string) =>
  ({ status, stake: m(stake), payout: m(payout) }) as Prediction

describe('summarize', () => {
  it('handles no settled predictions', () => {
    expect(summarize([p('open', '5000000', '0')])).toEqual({ settled: 0, wins: 0, winRatePct: '—', netDemo: '0' })
  })
  it('computes net and win rate in integers', () => {
    const s = summarize([p('won', '10000000', '18000000'), p('lost', '5000000', '0'), p('refunded', '7000000', '7000000')])
    expect(s.settled).toBe(2)
    expect(s.winRatePct).toBe('50')
    expect(s.netDemo).toBe('+3') // +8 - 5
  })
  it('shows a negative net', () => {
    expect(summarize([p('lost', '2500000', '0')]).netDemo).toBe('-2.5')
  })
})
