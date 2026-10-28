import { ArrowDown, ArrowUp, CalendarClock, CheckCircle2, Timer, TrendingUp } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useChart } from '../lib/queries'
import { countdown, dateTime, durationFull, price } from '../lib/format'
import { useCountdown } from '../lib/useCountdown'
import type { ChartRange, Market } from '../lib/types'
import { AssetIcon } from './AssetIcon'
import { PriceChart } from './PriceChart'
import { StakeSheet } from './StakeSheet'
import { Badge } from './shadcn/badge'
import { Button } from './shadcn/button'
import { Card } from './shadcn/card'
import { Spinner } from './ui'
import { cn } from '../lib/utils'

const RANGES: { value: ChartRange; label: string }[] = [
  { value: '1h', label: '1H' },
  { value: '6h', label: '6H' },
  { value: '24h', label: '24H' },
  { value: '7d', label: '7D' },
]

export type Direction = 'above' | 'below'

export function MarketCard({
  market,
  loadedAt,
  direction,
  onDirection,
  picker,
}: {
  market: Market
  loadedAt: number
  picker?: ReactNode
  direction: Direction | null
  onDirection: (d: Direction | null) => void
}) {
  const [range, setRange] = useState<ChartRange>('1h')
  const [sheetOpen, setSheetOpen] = useState(false)
  const chart = useChart(market.symbol, range)
  // `loadedAt` is when the server numbers were fetched; counting down from there keeps the timer honest.
  const secondsLeft = useCountdown(loadedAt + market.betting_closes_in_seconds * 1000)

  const bettingOpen = market.status === 'open' && market.feed_ok && secondsLeft > 0
  const change = chart.data?.change
  const up = change ? !change.abs.startsWith('-') : true
  const notice =
    market.status === 'paused'
      ? market.paused_by_feed
        ? 'Predictions are paused while the price feed recovers.'
        : `Predictions are paused${market.pause_reason ? `: ${market.pause_reason}` : '.'}`
      : market.status === 'open' && !market.feed_ok
        ? 'Price data is not fresh right now. Predictions are on hold.'
        : secondsLeft === 0
          ? 'Betting has closed for this market.'
          : null

  const live = bettingOpen
  return (
    <section className="space-y-3" aria-label={`${market.symbol} ${durationFull(market.duration_seconds)} market`}>
      {/* price + chart */}
      <Card className="overflow-hidden p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <AssetIcon symbol={market.symbol} size={44} />
            <div>
              <h2 className="font-display text-lg font-bold leading-tight text-white">{market.symbol}</h2>
              <p className="text-xs text-muted-foreground">{market.asset_name} · USD</p>
            </div>
          </div>
          <Badge variant={live ? 'up' : 'neutral'}>
            {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" aria-hidden />}
            {live ? 'Live' : market.status === 'paused' ? 'Paused' : 'Closed'}
          </Badge>
        </div>

        <div className="mt-4 flex items-end justify-between gap-2">
          <p className="font-display-num text-4xl font-bold text-white">{price(market.last_price)}</p>
          {change && (
            <Badge variant={up ? 'up' : 'down'} className="mb-1">
              {up ? '▲' : '▼'} {up ? '+' : ''}
              {change.pct}%
            </Badge>
          )}
        </div>

        <div className="mt-3 flex justify-end gap-1" role="tablist" aria-label="Chart range">
          {RANGES.map((item) => (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={range === item.value}
              onClick={() => setRange(item.value)}
              className={cn(
                'rounded-lg px-3 py-1 text-xs font-semibold transition-all duration-200',
                range === item.value ? 'bg-primary/20 text-primary-foreground ring-1 ring-primary/60' : 'text-muted-foreground hover:text-white',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="-mx-1 mt-1">
          {chart.isPending ? <Spinner /> : <PriceChart points={chart.data?.points ?? []} lastPrice={market.last_price} target={market.target_price} />}
        </div>
      </Card>

      {picker && <Card className="space-y-4 p-4">{picker}</Card>}

      {/* bet */}
      <Card className="p-4">
        <div className="grid grid-cols-3 divide-x divide-white/10 rounded-xl bg-black/25 py-2.5 text-center">
          <div className="px-2">
            <p className="flex items-center justify-center gap-1 text-[11px] text-muted-foreground">
              <Timer className="h-3 w-3 text-accent" /> Bets close in
            </p>
            <p className="font-display-num text-sm font-bold">{countdown(secondsLeft)}</p>
          </div>
          <div className="px-2">
            <p className="flex items-center justify-center gap-1 text-[11px] text-muted-foreground">
              <CalendarClock className="h-3 w-3 text-accent" /> Settles
            </p>
            <p className="whitespace-nowrap text-xs font-bold">{dateTime(market.closes_at)}</p>
          </div>
          <div className="px-2">
            <p className="text-[11px] text-muted-foreground">Odds</p>
            <p className="font-display-num text-sm font-bold text-gold">
              {market.odds_above}x · {market.odds_below}x
            </p>
                      </div>
        </div>

        <p className="mb-3 mt-4 text-sm font-semibold text-white">
          Will {market.symbol} be above or below <span className="font-display-num text-primary-foreground">{price(market.target_price)}</span>?
        </p>
        {notice && <p className="mb-3 rounded-lg bg-white/5 px-3 py-2 text-xs text-muted-foreground">{notice}</p>}
        <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="Your call">
          {(['above', 'below'] as const).map((d) => {
            const on = direction === d
            const Icon = d === 'above' ? ArrowUp : ArrowDown
            const odds = d === 'above' ? market.odds_above : market.odds_below
            return (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={!bettingOpen}
                onClick={() => onDirection(on ? null : d)}
                className={cn(
                  'relative flex flex-col gap-2 overflow-hidden rounded-2xl border p-3.5 text-left transition-all duration-300 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40',
                  on ? 'pick-selected scale-[1.02]' : 'pick-idle',
                )}
              >
                {on && <CheckCircle2 key={d} className="absolute right-2.5 top-2.5 h-5 w-5 animate-pop text-white" />}
                <span
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-xl transition-colors',
                    on ? 'bg-white/20 text-white' : d === 'above' ? 'bg-up/15 text-up' : 'bg-down/15 text-down',
                  )}
                >
                  <Icon className="h-6 w-6" strokeWidth={2.6} />
                </span>
                <span className="font-display text-base font-bold">{d === 'above' ? 'Above' : 'Below'}</span>
                <span className={cn('font-display-num text-sm font-semibold', on ? 'text-white' : 'text-slate-200')}>{price(market.target_price)}</span>
                <span className={cn('text-[11px]', on ? 'text-white/80' : 'text-muted-foreground')}>
                  Wins if price {d === 'above' ? '≥' : '<'} target
                </span>
                <span className={cn('inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold', on ? 'bg-white/20' : 'bg-gold/10 text-gold')}>
                  <TrendingUp className="h-3 w-3" /> {odds}x
                </span>
              </button>
            )
          })}
        </div>

        <Button size="lg" disabled={!bettingOpen || direction === null} onClick={() => setSheetOpen(true)} className="mt-4 w-full">
          {direction ? `Continue with ${direction === 'above' ? 'Above' : 'Below'} ${price(market.target_price)}` : 'Choose Above or Below'}
        </Button>
        <p className="mt-3 text-center text-[11px] text-muted-foreground">
          Demo credits only · no cash value · settled from the price at close
        </p>
      </Card>

      {sheetOpen && direction && (
        <StakeSheet market={market} direction={direction} onClose={() => setSheetOpen(false)} onPlaced={() => onDirection(null)} />
      )}
    </section>
  )
}
