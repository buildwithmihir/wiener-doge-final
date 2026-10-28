import { useInfiniteQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, History as HistoryIcon } from 'lucide-react'
import { api } from '../lib/api'
import { dateTime, durationLabel, price, usd } from '../lib/format'
import { FILTERS, summarize, type HistoryFilter } from '../lib/history'
import type { Prediction, PredictionStatus } from '../lib/types'
import { Badge, EmptyState, ErrorState, PageTitle, Spinner } from '../components/ui'

const PAGE = 20

function chipClass(active: boolean): string {
  return `shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition ${
    active ? 'bg-neon-blue/20 text-neon-blue ring-1 ring-neon-blue/60' : 'bg-white/5 text-slate-300 hover:text-white'
  }`
}

const STATUS_LABEL: Record<PredictionStatus, string> = {
  open: 'Open',
  won: 'Won',
  lost: 'Lost',
  refunded: 'Refunded',
}

function PredictionRow({ p }: { p: Prediction }) {
  const above = p.direction === 'above'
  const tone = p.status === 'won' ? 'up' : p.status === 'lost' ? 'down' : 'neutral'
  const Icon = above ? ArrowUp : ArrowDown
  return (
    <li className="glass-flat p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${above ? 'text-up' : 'text-down'}`} aria-hidden />
          <p className="font-semibold text-white">
            {p.symbol} {above ? 'ABOVE' : 'BELOW'} {price(p.target_price)}
          </p>
        </div>
        <Badge tone={tone}>{STATUS_LABEL[p.status]}</Badge>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        {durationLabel(p.duration_seconds)} market · placed {dateTime(p.created_at)}
      </p>
      <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <div>
          <p className="text-xs text-slate-500">Stake</p>
          <p className="num font-semibold">{usd(p.stake)}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">{p.status === 'open' ? 'Potential win' : 'Payout'}</p>
          <p className="num font-semibold">{usd(p.status === 'open' ? p.potential_payout : p.payout)}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">{p.settled_at ? 'Final price' : 'Closes'}</p>
          <p className="num font-semibold">{p.settled_at ? price(p.settle_price) : dateTime(p.closes_at)}</p>
        </div>
      </div>
    </li>
  )
}

export default function HistoryPage() {
  const [filter, setFilter] = useState<HistoryFilter>('all')

  const query = useInfiniteQuery({
    queryKey: ['predictions', filter],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const status = filter === 'all' ? '' : `&status=${filter}`
      const res = await api<{ items: Prediction[] }>(`/predictions?limit=${PAGE}&offset=${pageParam}${status}`)
      return res.items
    },
    getNextPageParam: (last, all) => (last.length < PAGE ? undefined : all.length * PAGE),
  })

  const items = useMemo(() => query.data?.pages.flat() ?? [], [query.data])
  const summary = useMemo(() => summarize(items), [items])

  return (
    <>
      <PageTitle icon={HistoryIcon} title="History" subtitle="Your predictions." />

      <div className="mb-3 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Filter predictions">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={chipClass(filter === f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {query.isPending && <Spinner />}
      {query.isError && <ErrorState message="Could not load your history." onRetry={() => void query.refetch()} />}

      {query.data && items.length === 0 && (
        <EmptyState title="No predictions yet" text="Place a prediction on the Markets tab and it will show up here." />
      )}

      {items.length > 0 && (
        <>
          <div className="glass-flat mb-3 grid grid-cols-3 gap-2 p-4 text-center">
            <div>
              <p className="text-xs text-slate-500">Settled</p>
              <p className="num text-lg font-semibold">{summary.settled}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Win rate</p>
              <p className="num text-lg font-semibold">{summary.winRatePct === '—' ? '—' : `${summary.winRatePct}%`}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Net (loaded)</p>
              <p
                className={`num text-lg font-semibold ${
                  summary.netDemo.startsWith('+') ? 'text-up' : summary.netDemo.startsWith('-') ? 'text-down' : ''
                }`}
              >
                {summary.netDemo === '0' ? '$0' : `${summary.netDemo[0]}${usd(summary.netDemo.slice(1))}`}
              </p>
            </div>
          </div>
          <ul className="space-y-3">
            {items.map((p) => (
              <PredictionRow key={p.id} p={p} />
            ))}
          </ul>
          {query.hasNextPage && (
            <button type="button" className="btn-ghost mt-4 w-full" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
              {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
            </button>
          )}
        </>
      )}
    </>
  )
}
