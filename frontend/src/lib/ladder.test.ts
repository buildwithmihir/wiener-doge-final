import { describe, expect, it } from 'vitest'
import { distancePct, nearestStrike, roundsFor } from './ladder'
import type { Market } from './types'

const m = (id: string, target: string, closes = '2026-10-25T00:00:00Z', dur = 86400, symbol = 'SOL') =>
  ({ id, target_price: target, closes_at: closes, duration_seconds: dur, symbol }) as Market

describe('ladder helpers', () => {
  it('groups by close time and sorts strikes ascending', () => {
    const rounds = roundsFor(
      [m('a', '110'), m('b', '90'), m('c', '100'), m('d', '100', '2026-10-26T00:00:00Z'), m('e', '5', undefined, 604800)],
      'SOL',
      86400,
    )
    expect(rounds).toHaveLength(2)
    expect(rounds[0]!.strikes.map((s) => s.id)).toEqual(['b', 'c', 'a'])
  })
  it('finds the nearest strike', () => {
    const s = [m('a', '90'), m('b', '100'), m('c', '110')]
    expect(nearestStrike(s, '104')!.id).toBe('b')
    expect(nearestStrike(s, '108')!.id).toBe('c')
    expect(nearestStrike(s, null)!.id).toBe('b')
    expect(nearestStrike([], '1')).toBeUndefined()
  })
  it('formats distance', () => {
    expect(distancePct('102', '100')).toBe('+2.0%')
    expect(distancePct('95', '100')).toBe('-5.0%')
    expect(distancePct('1', null)).toBeNull()
  })
})
