import { describe, expect, it } from 'vitest'
import { progressPct } from './vip'
import type { Money, VipTier } from './types'

const m = (u: number): Money => ({ units: String(u * 1_000_000), demo: String(u) })
const tier = (min: number): VipTier => ({
  id: 1, name: 'T', min_staked: m(min), reward: m(5), benefits: [], unlocked: false, achieved_at: null, reward_paid: false,
})

describe('progressPct', () => {
  it('is 0 with nothing staked', () => {
    expect(progressPct({ total_staked: m(0), current: null, next: tier(500) })).toBe(0)
  })
  it('measures from the current tier floor', () => {
    // between Bronze(500) and Silver(2000): 1250 staked -> 750/1500 = 50%
    expect(progressPct({ total_staked: m(1250), current: tier(500), next: tier(2000) })).toBe(50)
  })
  it('is 100 at the top tier and never exceeds 100', () => {
    expect(progressPct({ total_staked: m(99999), current: tier(500), next: null })).toBe(100)
    expect(progressPct({ total_staked: m(9999), current: null, next: tier(500) })).toBe(100)
  })
})
