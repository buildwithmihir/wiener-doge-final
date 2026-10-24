import { describe, expect, it } from 'vitest'
import { checkCreditAmount, multiplierToBps, validTargetPrice } from './admin'

describe('validTargetPrice', () => {
  it('accepts plain positive decimals', () => {
    for (const ok of ['119.40', '0.00001234', '1', ' 100 ']) expect(validTargetPrice(ok)).toBe(true)
  })
  it('rejects junk, zero, negatives, exponents and too many decimals', () => {
    for (const bad of ['', '0', '0.0', '-1', '1e5', 'abc', '1.', '.5', '1.1234567890123']) expect(validTargetPrice(bad)).toBe(false)
  })
})

describe('checkCreditAmount', () => {
  it('keeps the sign and exact text', () => {
    expect(checkCreditAmount('50')).toEqual({ ok: true, text: '50' })
    expect(checkCreditAmount('-12.5')).toEqual({ ok: true, text: '-12.5' })
    expect(checkCreditAmount('+3')).toEqual({ ok: true, text: '3' })
  })
  it('rejects zero, empty and invalid', () => {
    for (const bad of ['0', '-0', '', 'x', '1.1234567', '--5']) expect(checkCreditAmount(bad).ok).toBe(false)
  })
})

describe('multiplierToBps', () => {
  it('converts valid multipliers and rejects the rest', () => {
    expect(multiplierToBps('1.8')).toBe(18000)
    expect(multiplierToBps('1.85')).toBe(18500)
    expect(multiplierToBps('1')).toBeNull()
    expect(multiplierToBps('0.5')).toBeNull()
    expect(multiplierToBps('11')).toBeNull()
    expect(multiplierToBps('abc')).toBeNull()
  })
})
