import { BarChart3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { MarketCard, type Direction } from '../components/MarketCard'
import { AssetIcon } from '../components/AssetIcon'
import { Segmented } from '../components/Segmented'
import { StrikeLadder } from '../components/StrikeLadder'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { dateTime, durationFull } from '../lib/format'
import { nearestStrike, roundsFor } from '../lib/ladder'
import { useMarkets } from '../lib/queries'

export default function MarketsPage() {
  const markets = useMarkets()
  const [symbol, setSymbol] = useState<string | null>(null)
  const [duration, setDuration] = useState<number | null>(null)
  const [closesAt, setClosesAt] = useState<string | null>(null)
  const [marketId, setMarketId] = useState<string | null>(null)
  const [direction, setDirection] = useState<Direction | null>(null)

  if (markets.isPending) return <Spinner />
  if (markets.isError) return <ErrorState message="Could not load markets." onRetry={() => void markets.refetch()} />

  const all = markets.data
  if (all.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
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
  const rounds = roundsFor(all, activeSymbol, activeDuration)
  const round = rounds.find((r) => r.closesAt === closesAt) ?? rounds[0]!
  const active =
    round.strikes.find((m) => m.id === marketId) ?? nearestStrike(round.strikes, round.strikes[0]!.last_price) ?? round.strikes[0]!

  // Odds shown on each timeframe tab come from that timeframe's own markets.
  const oddsFor = (d: number) => ofSymbol.find((m) => m.duration_seconds === d)?.payout_multiplier

  return (
    <div className="space-y-4">
      <div className="flex gap-2" role="group" aria-label="Asset">
        {symbols.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setSymbol(s)
              setMarketId(null)
              setClosesAt(null)
            }}
            className={`flex items-center gap-2 rounded-2xl border px-3 py-1.5 text-sm font-bold transition duration-200 active:scale-95 ${
              s === activeSymbol ? 'pick-selected' : 'pick-idle'
            }`}
          >
            <AssetIcon symbol={s} size={24} /> {s}
          </button>
        ))}
      </div>

      <Segmented
        label="Timeframe"
        value={activeDuration}
        onChange={(d) => {
          setDuration(d)
          setMarketId(null)
          setClosesAt(null)
        }}
        options={durations.map((d) => ({
          value: d,
          label: durationFull(d),
          sub: oddsFor(d) ? `${oddsFor(d)}x odds` : undefined,
        }))}
      />

      {rounds.length > 1 && (
        <Segmented
          label="Round"
          value={round.closesAt}
          onChange={(c) => {
            setClosesAt(c)
            setMarketId(null)
          }}
          options={rounds.map((r) => ({ value: r.closesAt, label: `Closes ${dateTime(r.closesAt)}` }))}
        />
      )}

      {round.strikes.length > 1 && (
        <StrikeLadder
          strikes={round.strikes}
          selectedId={active.id}
          lastPrice={active.last_price}
          onSelect={(id) => setMarketId(id)}
        />
      )}

      <div key={active.id} className="animate-fade-up">
        <MarketCard market={active} loadedAt={markets.dataUpdatedAt} direction={direction} onDirection={setDirection} />
      </div>
    </div>
  )
}
