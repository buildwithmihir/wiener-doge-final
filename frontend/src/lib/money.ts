// DEMO amount math in integers (BigInt). Never uses floating point for credits.
const UNIT = 1_000_000n

/** "12.5" -> 12500000n. Returns null for anything that is not a plain amount with up to 6 decimals. */
export function parseDemoToUnits(text: string): bigint | null {
  const value = text.trim()
  if (!/^\d{1,12}(\.\d{1,6})?$/.test(value)) return null
  const [whole = '0', fraction = ''] = value.split('.')
  return BigInt(whole) * UNIT + BigInt(fraction.padEnd(6, '0'))
}

/** 1500000n -> "1.5", matching the server's formatting. */
export function unitsToDemo(units: bigint): string {
  const negative = units < 0n
  const abs = negative ? -units : units
  const whole = abs / UNIT
  const fraction = (abs % UNIT).toString().padStart(6, '0').replace(/0+$/, '')
  return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`
}

/** Same formula as the database: stake * multiplier, never less than the stake. "1.80" -> 1.8x. */
export function payoutUnits(stake: bigint, multiplier: string): bigint {
  const match = /^(\d+)(?:\.(\d{1,4}))?$/.exec(multiplier)
  if (!match) return stake
  const bps = BigInt(match[1] ?? '0') * 10000n + BigInt((match[2] ?? '').padEnd(4, '0'))
  const payout = (stake * bps) / 10000n
  return payout < stake ? stake : payout
}
