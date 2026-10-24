import { ArrowDown, ArrowUp, CalendarClock, CheckCircle2, Clock3, Crosshair, Timer, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { useChart } from '../lib/queries'
import { countdown, dateTime, durationFull, price } from '../lib/format'
import { useCountdown } from '../lib/useCountdown'
import type { ChartRange, Market } from '../lib/types'
import { AssetIcon } from './AssetIcon'
import { PriceChart } from './PriceChart'
import { StakeSheet } from './StakeSheet'
import { Badge, Spinner } from './ui'

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
}: {
  market: Market
  loadedAt: number
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

  return (
    <section className="glass p-4" aria-label={`${market.symbol} ${durationFull(market.duration_seconds)} market`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AssetIcon symbol={market.symbol} />
          <div>
            <h2 className="text-2xl font-bold leading-tight text-white">{market.symbol}</h2>
            <p className="flex items-center gap-1.5 text-sm text-slate-300">
              {durationFull(market.duration_seconds)} <Clock3 className="h-3.5 w-3.5" />
            </p>
          </div>
        </div>
        <Badge tone={bettingOpen ? 'up' : 'neutral'}>{bettingOpen ? 'Open' : market.status === 'paused' ? 'Paused' : 'Closed'}</Badge>
      </div>

      <div className="mt-4 flex items-end justify-between gap-2 border-t border-white/10 pt-4">
        <div>
          <p className="num text-4xl font-bold text-white">{price(market.last_price)}</p>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-300">
            <Crosshair className="h-4 w-4 text-neon-blue" /> Target {price(market.target_price)}
          </p>
        </div>
        {change && (
          <p className={`num pb-5 text-sm font-semibold ${up ? 'text-up' : 'text-down'}`}>
            {up ? '▲' : '▼'} {up ? '+' : ''}
            {change.abs} ({up ? '+' : ''}
            {change.pct}%)
          </p>
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
            className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
              range === item.value ? 'bg-neon-blue text-white shadow-glow' : 'text-slate-400 hover:text-white'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="mt-2 rounded-xl border border-white/10 bg-ink-900/60 p-2">
        {chart.isPending ? <Spinner /> : <PriceChart points={chart.data?.points ?? []} lastPrice={market.last_price} target={market.target_price} />}
      </div>

      <div className="glass-flat mt-3 grid grid-cols-2 divide-x divide-white/10 p-3">
        <div className="flex items-center gap-3 pr-3">
          <Timer className="h-7 w-7 shrink-0 text-neon-violet" />
          <div>
            <p className="text-xs text-slate-400">Betting closes in</p>
            <p className="num text-lg font-bold">{countdown(secondsLeft)}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 pl-3">
          <CalendarClock className="h-7 w-7 shrink-0 text-neon-violet" />
          <div>
            <p className="text-xs text-slate-400">Market closes</p>
            <p className="text-sm font-semibold">{dateTime(market.closes_at)}</p>
          </div>
        </div>
      </div>

      <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Will {market.symbol} be above or below {price(market.target_price)}?
      </p>
      {notice && <p className="mb-2 rounded-lg bg-white/5 px-3 py-2 text-xs text-slate-300">{notice}</p>}
      <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="Your call">
        {(['above', 'below'] as const).map((d) => {
          const on = direction === d
          const Icon = d === 'above' ? ArrowUp : ArrowDown
          return (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={on}
              disabled={!bettingOpen}
              onClick={() => onDirection(on ? null : d)}
              className={`relative flex flex-col gap-1 rounded-2xl border px-3 py-3 text-left transition duration-200 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40 ${
                on ? 'pick-selected' : 'pick-idle'
              }`}
            >
              {on && <CheckCircle2 key={d} className="absolute right-2 top-2 h-5 w-5 animate-pop text-white" />}
              <span className="flex items-center gap-2">
                <Icon className={`h-7 w-7 transition-colors ${on ? 'text-white' : d === 'above' ? 'text-up' : 'text-down'}`} />
                <span className="text-base font-bold">{d === 'above' ? 'ABOVE' : 'BELOW'}</span>
              </span>
              <span className={`num text-sm font-semibold ${on ? 'text-white' : 'text-slate-200'}`}>{price(market.target_price)}</span>
              <span className={`text-[11px] ${on ? 'text-white/80' : 'text-slate-400'}`}>
                Wins if {d === 'above' ? '≥' : '<'} target at close
              </span>
              <span className={`mt-1 inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${on ? 'bg-white/20' : 'bg-white/5 text-gold'}`}>
                <TrendingUp className="h-3 w-3" /> {market.payout_multiplier}x
              </span>
            </button>
          )
        })}
      </div>

      <button
        type="button"
        disabled={!bettingOpen || direction === null}
        onClick={() => setSheetOpen(true)}
        className="btn-primary mt-3 w-full"
      >
        {direction
          ? `Continue · ${direction === 'above' ? 'ABOVE' : 'BELOW'} ${price(market.target_price)} · ${market.payout_multiplier}x`
          : 'Pick Above or Below'}
      </button>
      <p className="mt-3 text-center text-[11px] text-slate-500">
        Simulated payout {market.payout_multiplier}x · demo credits only · settled from the price at close
      </p>

      {sheetOpen && direction && (
        <StakeSheet
          market={market}
          direction={direction}
          onClose={() => setSheetOpen(false)}
          onPlaced={() => onDirection(null)}
        />
      )}
    </section>
  )
}
