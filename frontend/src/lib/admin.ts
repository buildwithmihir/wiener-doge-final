import { parseDemoToUnits } from './money'

export const ADMIN_DURATIONS: { seconds: number; label: string }[] = [
  { seconds: 86400, label: '24h' },
  { seconds: 172800, label: '48h' },
  { seconds: 604800, label: '7d' },
  { seconds: 2592000, label: '30d' },
]

/** A target price must be a plain positive decimal with at most 12 decimals (the database precision). */
export function validTargetPrice(text: string): boolean {
  const t = text.trim()
  return /^\d{1,24}(\.\d{1,12})?$/.test(t) && /[1-9]/.test(t)
}

export type AmountCheck = { ok: true; text: string } | { ok: false; error: string }

/** Signed DEMO amount for credit adjustments: "50", "-12.5". Never zero. Returns the exact text to send. */
export function checkCreditAmount(input: string): AmountCheck {
  const t = input.trim()
  const negative = t.startsWith('-')
  const body = negative ? t.slice(1) : t.startsWith('+') ? t.slice(1) : t
  const units = parseDemoToUnits(body)
  if (units === null) return { ok: false, error: 'Enter a number like 50 or -12.5 (max 6 decimals).' }
  if (units === 0n) return { ok: false, error: 'Amount cannot be zero.' }
  return { ok: true, text: `${negative ? '-' : ''}${body}` }
}
