import type { Money } from './types'

/** "1234.5" -> "1,234.5" (text in, text out: no floating point). */
export function withCommas(amount: string): string {
  const negative = amount.startsWith('-')
  const [whole = '0', fraction] = (negative ? amount.slice(1) : amount).split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}${fraction ? `.${fraction}` : ''}`
}

/** DEMO amounts are shown with a "$" like the design, always next to a DEMO badge in the UI. */
export function usd(money: Money | string, maxDecimals = 2): string {
  const raw = typeof money === 'string' ? money : money.demo
  const [whole = '0', fraction = ''] = raw.replace(/^-/, '').split('.')
  const trimmed = fraction.slice(0, maxDecimals).replace(/0+$/, '')
  const body = withCommas(`${whole}${trimmed ? `.${trimmed}` : ''}`)
  return `${raw.startsWith('-') ? '-' : ''}$${body}`
}

/**
 * Market prices. Prices of 1 or more (SOL etc.) show exactly 2 decimals ("119.40").
 * Prices below 1 (tiny tokens like WIENER) keep their full precision, otherwise they would show as "0.00".
 */
export function price(value: string | null | undefined): string {
  if (!value) return '—'
  const n = Number(value)
  if (Number.isFinite(n) && n >= 1) return withCommas(n.toFixed(2))
  return withCommas(value)
}

export function durationLabel(seconds: number): string {
  const labels: Record<number, string> = { 86400: '24h', 172800: '48h', 604800: '7d', 2592000: '30d' }
  return labels[seconds] ?? `${Math.round(seconds / 3600)}h`
}

export function durationFull(seconds: number): string {
  const labels: Record<number, string> = { 86400: 'Next 24 Hours', 172800: 'Next 48 Hours', 604800: 'Next 7 Days', 2592000: 'Next 30 Days' }
  return labels[seconds] ?? `Next ${Math.round(seconds / 3600)} Hours`
}

/** 85800 -> "23h 50m", 3000 -> "50m", 45 -> "45s", 0 -> "0s". */
export function countdown(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m`
  return `${seconds}s`
}

export function dateTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}