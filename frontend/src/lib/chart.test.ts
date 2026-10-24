import { describe, expect, it } from 'vitest'
import { buildPlot, priceDecimals, type PlotBox } from './chart'

const BOX: PlotBox = { width: 300, height: 200, left: 10, right: 50, top: 10, bottom: 20 }
const pts = (prices: string[]) =>
  prices.map((price, i) => ({ t: new Date(Date.UTC(2026, 9, 18, 12, i)).toISOString(), price }))

describe('buildPlot', () => {
  it('needs at least two valid points', () => {
    expect(buildPlot([], BOX)).toBeNull()
    expect(buildPlot(pts(['100']), BOX)).toBeNull()
    expect(buildPlot([{ t: 'nope', price: 'x' }, { t: 'bad', price: '1' }], BOX)).toBeNull()
  })

  it('keeps every point inside the drawing box and puts higher prices higher up', () => {
    const plot = buildPlot(pts(['100', '101', '99', '102']), BOX)!
    expect(plot.line.startsWith('M10.0')).toBe(true)
    expect(plot.last.x).toBeCloseTo(250, 5) // right edge of the plot area
    for (const tick of plot.ticks) {
      expect(tick.y).toBeGreaterThanOrEqual(BOX.top - 0.01)
      expect(tick.y).toBeLessThanOrEqual(BOX.height - BOX.bottom + 0.01)
    }
    const rising = buildPlot(pts(['100', '101', '102']), BOX)!
    expect(rising.last.y).toBeLessThan(10 + (200 - 10 - 20)) // inside the box
    expect(rising.line.split(' ')[1]!.length).toBeGreaterThan(0)
    const [, firstY] = rising.line.slice(1).split(' L')[0]!.split(' ')
    expect(rising.last.y).toBeLessThan(Number(firstY)) // price went up, so the line ends higher on screen
    expect(plot.ticks[0]!.value).toBeGreaterThan(plot.ticks[4]!.value)
  })

  it('draws a flat line when the price does not move', () => {
    const plot = buildPlot(pts(['5', '5', '5']), BOX)!
    expect(Number.isFinite(plot.last.y)).toBe(true)
    expect(plot.max).toBeGreaterThan(plot.min)
  })

  it('chooses enough decimals for tiny prices', () => {
    expect(priceDecimals(118, 119.5)).toBe(2)
    expect(priceDecimals(0.0001, 0.00012)).toBeGreaterThanOrEqual(6)
    expect(priceDecimals(5, 5)).toBe(2)
  })
})

describe('buildPlot target line', () => {
  it('has no target line by default', () => {
    expect(buildPlot(pts(['100', '101']), BOX)!.targetY).toBeNull()
  })
  it('places a nearby target inside the plot and a far one clamped to the edge', () => {
    const near = buildPlot(pts(['100', '101', '102']), BOX, 5, 102.5)!
    expect(near.targetOff).toBeNull()
    expect(near.targetY!).toBeGreaterThanOrEqual(BOX.top)
    expect(near.targetY!).toBeLessThanOrEqual(BOX.height - BOX.bottom)
    const far = buildPlot(pts(['100', '101', '102']), BOX, 5, 500)!
    expect(far.targetOff).toBe('above')
    const low = buildPlot(pts(['100', '101', '102']), BOX, 5, 1)!
    expect(low.targetOff).toBe('below')
  })
})
