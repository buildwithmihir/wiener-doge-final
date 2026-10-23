import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MarketCard } from '../components/MarketCard'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { durationLabel, price } from '../lib/format'
import { useMarkets } from '../lib/queries'

function chipClass(active: boolean): string {
  return `rounded-xl px-3 py-1.5 text-sm font-semibold transition ${
    active ? 'bg-neon-blue/20 text-neon-blue ring-1 ring-neon-blue/60' : 'bg-white/5 text-slate-300 hover:text-white'
  }`
}

export default function MarketsPage() {
  const markets = useMarkets()
  const [symbol, setSymbol] = useState<string | null>(null)
  const [duration, setDuration] = useState<number | null>(null)
  const [marketId, setMarketId] = useState<string | null>(null)

  if (markets.isPending) return <Spinner />
  if (markets.isError) return <ErrorState message="Could not load markets." onRetry={() => void markets.refetch()} />

  const all = markets.data
  if (all.length === 0) {
    return (
      <EmptyState
        title="No open markets yet"
        text="New markets are added by the team. Check back soon."
        action={
          <Link to="/wallet" className="btn-ghost">
            View wallet
          </Link>
        }
      />
    )
  }

  const symbols = [...new Set(all.map((m) => m.symbol))]
  const activeSymbol = symbol && symbols.includes(symbol) ? symbol : symbols[0]!
  const ofSymbol = all.filter((m) => m.symbol === activeSymbol)
  const durations = [...new Set(ofSymbol.map((m) => m.duration_seconds))].sort((a, b) => a - b)
  const activeDuration = duration && durations.includes(duration) ? duration : durations[0]!
  const candidates = ofSymbol
    .filter((m) => m.duration_seconds === activeDuration)
    .sort((a, b) => Number(a.target_price) - Number(b.target_price))
  const active = candidates.find((m) => m.id === marketId) ?? candidates[0]!

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Asset">
        {symbols.map((s) => (
          <button key={s} type="button" className={chipClass(s === activeSymbol)} onClick={() => setSymbol(s)}>
            {s}
          </button>
        ))}
        <span className="mx-1 w-px bg-white/10" aria-hidden />
        {durations.map((d) => (
          <button key={d} type="button" className={chipClass(d === activeDuration)} onClick={() => setDuration(d)}>
            {durationLabel(d)}
          </button>
        ))}
      </div>

      {candidates.length > 1 && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Target price">
          <span className="text-xs text-slate-400">Target</span>
          {candidates.map((m) => (
            <button key={m.id} type="button" className={chipClass(m.id === active.id)} onClick={() => setMarketId(m.id)}>
              {price(m.target_price)}
            </button>
          ))}
        </div>
      )}

      <MarketCard key={active.id} market={active} loadedAt={markets.dataUpdatedAt} />
    </div>
  )
}
