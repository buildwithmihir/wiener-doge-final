

  
import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AssetIcon } from '../components/AssetIcon'
import { Badge, EmptyState, ErrorState, Spinner } from '../components/ui'
import { price } from '../lib/format'
import { useAssets } from '../lib/queries'

export default function MarketsPage() {
  const assets = useAssets()
  return (
    <div>
      <h1 className="font-display mb-4 mt-1 bg-gradient-to-r from-neon-cyan via-neon-blue to-neon-violet bg-clip-text text-3xl font-extrabold text-transparent">
        Markets available
      </h1>
      {assets.isPending && <Spinner />}
      {assets.isError && <ErrorState message="Could not load markets." onRetry={() => void assets.refetch()} />}
      {assets.data?.length === 0 && <EmptyState title="No assets yet" text="Check back soon." />}
      <ul className="space-y-3">
        {assets.data?.map((a) => {
          const up = a.change_pct ? !a.change_pct.startsWith('-') : true
          return (
            <li key={a.symbol}>
              <Link to={`/market/${a.symbol}`} className="glass flex animate-fade-up items-center gap-4 p-4 transition active:scale-[0.98]">
                <AssetIcon symbol={a.symbol} size={52} />
                <div className="min-w-0 flex-1">
                  <p className="font-display text-lg font-bold text-white">{a.symbol}</p>
                  <p className="text-xs text-slate-400">
                    {a.name} · {a.open_markets} market{a.open_markets === 1 ? '' : 's'}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-display-num text-lg font-bold text-white">{a.last_price ? `$${price(a.last_price)}` : '—'}</p>
                  {a.change_pct ? (
                    <Badge tone={up ? 'up' : 'down'}>
                      {up ? '▲ +' : '▼ '}
                      {a.change_pct}%
                    </Badge>
                  ) : (
                    <p className="text-xs text-slate-500">24h n/a</p>
                  )}
                </div>
                <ChevronRight className="h-5 w-5 text-slate-500" aria-hidden />
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}