import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useState } from 'react'
import { MarketCard, type Direction } from '../components/MarketCard'
import { AssetIcon } from '../components/AssetIcon'
import { Segmented } from '../components/Segmented'
import { StrikeLadder } from '../components/StrikeLadder'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { dateTime, durationFull } from '../lib/format'
import { nearestStrike, roundsFor } from '../lib/ladder'
import { useMarkets } from '../lib/queries'

export default function MarketDetailPage() {
  const { symbol = '' } = useParams()
  const markets = useMarkets()
  const [duration, setDuration] = useState<number | null>(null)
  const [closesAt, setClosesAt] = useState<string | null>(null)
  const [marketId, setMarketId] = useState<string | null>(null)
  const [direction, setDirection] = useState<Direction | null>(null)

  const back = (
    <Link to="/" className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300 hover:text-white">
      <ArrowLeft className="h-4 w-4" /> <AssetIcon symbol={symbol} size={26} /> {symbol}
    </Link>
  )

  if (markets.isPending) return <Spinner />
  if (markets.isError) return <ErrorState message="Could not load markets." onRetry={() => void markets.refetch()} />

  const ofSymbol = markets.data.filter((m) => m.symbol === symbol)
  if (ofSymbol.length === 0) {
    return (
      <>
        {back}
        <EmptyState title={`No open ${symbol} markets`} text="New markets are added by the team. Check back soon." />
      </>
    )
  }

  const durations = [...new Set(ofSymbol.map((m) => m.duration_seconds))].sort((a, b) => a - b)
  const activeDuration = duration && durations.includes(duration) ? duration : durations[0]!
  const rounds = roundsFor(markets.data, symbol, activeDuration)
  const round = rounds.find((r) => r.closesAt === closesAt) ?? rounds[0]!
  const strikes = nearbyStrikes(round.strikes, round.strikes[0]!.last_price)
  const active = strikes.find((m) => m.id === marketId) ?? nearestStrike(strikes, strikes[0]!.last_price) ?? strikes[0]!

  const picker = (
    <>
      <Segmented
        label="Timeframe"
        value={activeDuration}
        onChange={(d) => { setDuration(d); setMarketId(null); setClosesAt(null); setDirection(null) }}
        options={durations.map((d) => ({ value: d, label: durationFull(d) }))}
      />
      {rounds.length > 1 && (
        <Segmented
          label="Round"
          value={round.closesAt}
          onChange={(c) => { setClosesAt(c); setMarketId(null) }}
          options={rounds.map((r) => ({ value: r.closesAt, label: `Closes ${dateTime(r.closesAt)}` }))}
        />
      )}
      {strikes.length > 1 && (
        <StrikeLadder strikes={strikes} selectedId={active.id} lastPrice={active.last_price} onSelect={(id) => setMarketId(id)} />
      )}
    </>
  )

  return (
    <div className="space-y-3">
      {back}
      <div key={`${symbol}-${activeDuration}`} className="animate-fade-up">
        <MarketCard market={active} loadedAt={markets.dataUpdatedAt} direction={direction} onDirection={setDirection} picker={picker} />
      </div>
    </div>
  )
}