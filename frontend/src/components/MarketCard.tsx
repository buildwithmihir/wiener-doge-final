import { ArrowDown, ArrowUp, CalendarClock, Clock3, Crosshair, Timer } from 'lucide-react'
import { useState } from 'react'
import { useChart } from '../lib/queries'
import { countdown, dateTime, durationLabel, price } from '../lib/format'
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

export function MarketCard({ market, loadedAt }: { market: Market; loadedAt: number }) {
  const [range, setRange] = useState<ChartRange>('1h')
  const [direction, setDirection] = useState<'above' | 'below' | null>(null)
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
    <section className="glass p-4" aria-label={`${market.symbol} ${durationLabel(market.duration_seconds)} market`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AssetIcon symbol={market.symbol} />
          <div>
            <h2 className="text-2xl font-bold leading-tight text-white">{market.symbol}</h2>
            <p className="flex items-center gap-1.5 text-sm text-slate-300">
              {durationLabel(market.duration_seconds)} market <Clock3 className="h-3.5 w-3.5" />
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
        {chart.isPending ? <Spinner /> : <PriceChart points={chart.data?.points ?? []} lastPrice={market.last_price} />}
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

      <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">Your call</p>
      {notice && <p className="mb-2 rounded-lg bg-white/5 px-3 py-2 text-xs text-slate-300">{notice}</p>}
      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          disabled={!bettingOpen}
          onClick={() => setDirection('above')}
          className="flex items-center gap-3 rounded-xl border border-up/50 bg-up-soft px-3 py-3 text-left shadow-glow-up transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowUp className="h-9 w-9 text-up" />
          <span>
            <span className="block text-base font-bold text-up">ABOVE</span>
            <span className="block text-[11px] text-slate-300">Wins if ≥ {price(market.target_price)}</span>
          </span>
        </button>
        <button
          type="button"
          disabled={!bettingOpen}
          onClick={() => setDirection('below')}
          className="flex items-center gap-3 rounded-xl border border-down/50 bg-down-soft px-3 py-3 text-left shadow-glow-down transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowDown className="h-9 w-9 text-down" />
          <span>
            <span className="block text-base font-bold text-down">BELOW</span>
            <span className="block text-[11px] text-slate-300">Wins if &lt; {price(market.target_price)}</span>
          </span>
        </button>
      </div>
      <p className="mt-3 text-center text-[11px] text-slate-500">
        Simulated payout {market.payout_multiplier}x · demo credits only · settled from the price at close
      </p>

      {direction && <StakeSheet market={market} direction={direction} onClose={() => setDirection(null)} />}
    </section>
  )
}
