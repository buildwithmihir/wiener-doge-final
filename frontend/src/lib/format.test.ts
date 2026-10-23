import { describe, expect, it } from 'vitest'
import { countdown, durationLabel, price, usd, withCommas } from './format'

describe('format', () => {
  it('adds thousands separators without touching decimals', () => {
    expect(withCommas('1234567.891')).toBe('1,234,567.891')
    expect(withCommas('999')).toBe('999')
    expect(withCommas('-1000')).toBe('-1,000')
  })

  it('shows DEMO amounts with a $ and at most 2 decimals', () => {
    expect(usd('1000')).toBe('$1,000')
    expect(usd('12.5')).toBe('$12.5')
    expect(usd('0.123456')).toBe('$0.12')
    expect(usd('-12.5')).toBe('-$12.5')
    expect(usd({ units: '25000000', demo: '25' })).toBe('$25')
    expect(usd('0.001')).toBe('$0')
  })

  it('keeps market prices at full precision', () => {
    expect(price('119.4')).toBe('119.4')
    expect(price('0.00012345')).toBe('0.00012345')
    expect(price(null)).toBe('—')
  })

  it('formats countdowns', () => {
    expect(countdown(85800)).toBe('23h 50m')
    expect(countdown(3000)).toBe('50m')
    expect(countdown(45)).toBe('45s')
    expect(countdown(-5)).toBe('0s')
    expect(countdown(2 * 86400 + 5 * 3600)).toBe('2d 5h')
  })

  it('labels durations', () => {
    expect(durationLabel(86400)).toBe('24h')
    expect(durationLabel(604800)).toBe('7d')
    expect(durationLabel(7200)).toBe('2h')
  })
})
