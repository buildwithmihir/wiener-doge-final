import { describe, expect, it } from 'vitest'
import { checkCreditAmount, validTargetPrice } from './admin'

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
