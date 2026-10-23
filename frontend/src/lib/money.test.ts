import { describe, expect, it } from 'vitest'
import { parseDemoToUnits, payoutUnits, unitsToDemo } from './money'

describe('money', () => {
  it('parses plain DEMO amounts to base units', () => {
    expect(parseDemoToUnits('10')).toBe(10_000_000n)
    expect(parseDemoToUnits(' 12.5 ')).toBe(12_500_000n)
    expect(parseDemoToUnits('0.000001')).toBe(1n)
    expect(parseDemoToUnits('0')).toBe(0n)
  })

  it('rejects anything else', () => {
    for (const bad of ['', 'abc', '-5', '1e3', '1.0000001', '1,5', '.5', '5.', '1 000', '9'.repeat(13)]) {
      expect(parseDemoToUnits(bad), bad).toBeNull()
    }
  })

  it('formats base units like the server does', () => {
    expect(unitsToDemo(1_500_000n)).toBe('1.5')
    expect(unitsToDemo(1_000_000_000n)).toBe('1000')
    expect(unitsToDemo(1n)).toBe('0.000001')
    expect(unitsToDemo(-2_500_000n)).toBe('-2.5')
  })

  it('round-trips', () => {
    for (const text of ['0', '1', '0.5', '999.999999', '123456.1']) {
      expect(unitsToDemo(parseDemoToUnits(text)!)).toBe(text)
    }
  })

  it('computes the simulated payout exactly like the database', () => {
    expect(payoutUnits(25_000_000n, '1.80')).toBe(45_000_000n)
    expect(payoutUnits(1n, '1.80')).toBe(1n) // never below the stake
    expect(payoutUnits(1_000_000n, '1.0001')).toBe(1_000_100n)
    expect(payoutUnits(10_000_000n, 'garbage')).toBe(10_000_000n)
  })
})
