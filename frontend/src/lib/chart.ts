
 // Turns price points into SVG geometry. Plotting uses numbers; every PRICE SHOWN to the user
// still comes from the server's text values.
import type { ChartResponse } from './types'

export interface Plot {
  line: string
  area: string
  last: { x: number; y: number }
  ticks: { y: number; value: number }[]
  min: number
  max: number
  decimals: number
  /** Y of the target line (clamped inside the plot) and whether the real target is off the chart. */
  targetY: number | null
  targetOff: 'above' | 'below' | null
  dots: { x: number; y: number; t: string; price: string }[]
}

export interface PlotBox {
  width: number
  height: number
  left: number
  right: number
  top: number
  bottom: number
}

/** Enough decimals that neighbouring axis labels differ (SOL ~2, a tiny token ~7). */
export function priceDecimals(min: number, max: number): number {
  if (min >= 1) return 2
  const step = (max - min) / 4

  if (!(step > 0)) return 2

  return Math.max(2, Math.min(10, Math.ceil(-Math.log10(step)) + 1))
}

export function buildPlot(
  points: ChartResponse['points'],
  box: PlotBox,
  tickCount = 5,
  target?: number | null,
): Plot | null {
  const data = points
    .map((p) => ({
      t: Date.parse(p.t),
      v: Number(p.price),
      raw: p,
    }))
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v))

  if (data.length < 2) return null

  const t0 = data[0]!.t
  const t1 = data[data.length - 1]!.t

  let lo = Math.min(...data.map((p) => p.v))
  let hi = Math.max(...data.map((p) => p.v))

  if (hi === lo) {
    lo -= Math.abs(lo) * 0.001 || 0.5
    hi += Math.abs(hi) * 0.001 || 0.5
  }

  // Pull the axis toward the target only when it is reasonably close,
  // so the line stays readable.
  const span = hi - lo
  const hasTarget = target != null && Number.isFinite(target) && target > 0

  if (
    hasTarget &&
    Math.abs(target - (target > hi ? hi : lo)) <= span * 3 &&
    (target > hi || target < lo)
  ) {
    if (target > hi) {
      hi = target
    } else {
      lo = target
    }
  }

  const pad = (hi - lo) * 0.08
  const min = lo - pad
  const max = hi + pad

  const innerW = box.width - box.left - box.right
  const innerH = box.height - box.top - box.bottom

  const x = (t: number) =>
    box.left +
    (t1 === t0 ? innerW : ((t - t0) / (t1 - t0)) * innerW)

  const y = (v: number) =>
    box.top + (1 - (v - min) / (max - min)) * innerH

  const coords = data.map((p) => [x(p.t), y(p.v)] as const)

  const dots = data.map((p, i) => ({
    x: coords[i]![0],
    y: coords[i]![1],
    t: p.raw.t,
    price: p.raw.price,
  }))

  const line = coords
    .map(([cx, cy], i) => `${i === 0 ? 'M' : 'L'}${cx.toFixed(1)} ${cy.toFixed(1)}`)
    .join(' ')

  const baseline = (box.top + innerH).toFixed(1)
  const first = coords[0]!
  const last = coords[coords.length - 1]!

  const area = `${line} L${last[0].toFixed(1)} ${baseline} L${first[0].toFixed(1)} ${baseline} Z`

  const ticks = Array.from({ length: tickCount }, (_, i) => {
    const value = max - ((max - min) * i) / (tickCount - 1)

    return {
      y: y(value),
      value,
    }
  })

  let targetY: number | null = null
  let targetOff: 'above' | 'below' | null = null

  if (hasTarget) {
    if (target > max) {
      targetOff = 'above'
      targetY = box.top + 2
    } else if (target < min) {
      targetOff = 'below'
      targetY = box.top + innerH - 2
    } else {
      targetY = y(target)
    }
  }

  return {
    line,
    area,
    last: {
      x: last[0],
      y: last[1],
    },
    ticks,
    min,
    max,
    decimals: priceDecimals(min, max),
    targetY,
    targetOff,
    dots,
  }
}
