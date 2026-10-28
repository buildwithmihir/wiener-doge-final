import { useQuery } from '@tanstack/react-query'
import { Crown, Trophy } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import type { LeaderboardMetric, LeaderboardPeriod, LeaderboardResponse, LeaderboardRow } from '../lib/types'
import { EmptyState, ErrorState, PageTitle, Spinner } from '../components/ui'

const METRICS: { key: LeaderboardMetric; label: string }[] = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'wagered', label: 'Wagered' },
]
const PERIODS: { key: LeaderboardPeriod; label: string }[] = [
  { key: 'all', label: 'All time' },
  { key: 'weekly', label: '7 days' },
  { key: 'monthly', label: '30 days' },
]

function chipClass(active: boolean): string {
  return `shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition ${
    active ? 'bg-neon-blue/20 text-neon-blue ring-1 ring-neon-blue/60' : 'bg-white/5 text-slate-300 hover:text-white'
  }`
}

function Podium({ rows, metric }: { rows: LeaderboardRow[]; metric: LeaderboardMetric }) {
  const val = (r: LeaderboardRow) =>
    metric === 'accuracy' ? (r.accuracy_pct === null ? '—' : `${r.accuracy_pct}%`) : usd(r.staked)
  // visual order: 2nd, 1st, 3rd
  const slots = [
    { r: rows[1], place: 2, h: 'h-20', c: 'from-[#5b6477] to-[#a9b2c6]', t: 'text-silver' },
    { r: rows[0], place: 1, h: 'h-28', c: 'from-[#b8791a] to-[#f5b942]', t: 'text-gold' },
    { r: rows[2], place: 3, h: 'h-16', c: 'from-[#8a4b1f] to-[#e8924d]', t: 'text-bronze' },
  ]
  return (
    <div className="mb-4 grid grid-cols-3 items-end gap-2">
      {slots.map(({ r, place, h, c, t }) =>
        r ? (
          <div key={place} className="min-w-0 text-center">
            <Crown className={`mx-auto h-6 w-6 ${t}`} aria-hidden />
            <p className="truncate text-sm font-semibold text-white">
              {r.alias}
              {r.is_me && <span className="ml-1 text-[10px] text-neon-blue">you</span>}
            </p>
            <p className="num text-xs text-slate-300">{val(r)}</p>
            <div
              className={`mt-2 flex ${h} items-start justify-center rounded-t-2xl bg-gradient-to-b ${c} pt-2 font-display text-2xl font-extrabold text-white ${
                r.is_me ? 'ring-2 ring-white/70' : ''
              }`}
            >
              {place}
            </div>
          </div>
        ) : (
          <div key={place} />
        ),
      )}
    </div>
  )
}

function Row({ r, metric }: { r: LeaderboardRow; metric: LeaderboardMetric }) {
  const main = metric === 'accuracy' ? (r.accuracy_pct === null ? '—' : `${r.accuracy_pct}%`) : usd(r.staked)
  const sub =
    metric === 'accuracy' ? `${r.wins}/${r.settled} won` : `${r.settled} settled · ${r.accuracy_pct ?? '—'}${r.accuracy_pct === null ? '' : '%'}`
  return (
    <li className={`glass-flat flex items-center gap-3 p-3 ${r.is_me ? 'ring-1 ring-neon-blue/60' : ''}`}>
      <span className={`num flex w-8 justify-center text-sm font-bold ${r.rank === 1 ? 'text-gold' : r.rank === 2 ? 'text-silver' : r.rank === 3 ? 'text-bronze' : 'text-slate-300'}`}>
        {r.rank <= 3 ? <Crown className="h-5 w-5" aria-label={`Rank ${r.rank}`} /> : `#${r.rank}`}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-white">
          {r.alias}
          {r.is_me && <span className="ml-2 text-xs text-neon-blue">you</span>}
        </p>
        <p className="text-xs text-slate-400">{sub}</p>
      </div>
      <p className="num text-lg font-bold text-white">{main}</p>
    </li>
  )
}

export default function LeaderboardPage() {
  const [metric, setMetric] = useState<LeaderboardMetric>('accuracy')
  const [period, setPeriod] = useState<LeaderboardPeriod>('all')

  const lb = useQuery({
    queryKey: ['leaderboard', metric, period],
    queryFn: () => api<LeaderboardResponse>(`/leaderboard?metric=${metric}&period=${period}`),
  })

  const meInList = lb.data?.items.some((i) => i.is_me) ?? false
  const showPodium = (lb.data?.items.length ?? 0) >= 3
  const listRows = lb.data ? (showPodium ? lb.data.items.slice(3) : lb.data.items) : []

  return (
    <>
      <PageTitle icon={Trophy} title="Leaderboard" subtitle="Prediction rankings. Names are first names or aliases only." />
      <div className="mb-2 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Ranking metric">
        {METRICS.map((m) => (
          <button key={m.key} type="button" role="tab" aria-selected={metric === m.key} className={chipClass(metric === m.key)} onClick={() => setMetric(m.key)}>
            {m.label}
          </button>
        ))}
      </div>
      <div className="mb-3 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Period">
        {PERIODS.map((p) => (
          <button key={p.key} type="button" role="tab" aria-selected={period === p.key} className={chipClass(period === p.key)} onClick={() => setPeriod(p.key)}>
            {p.label}
          </button>
        ))}
      </div>

      {lb.isPending && <Spinner />}
      {lb.isError && <ErrorState message="Could not load the leaderboard." onRetry={() => void lb.refetch()} />}
      {lb.data && lb.data.items.length === 0 && (
        <EmptyState
          title="No one ranked yet"
          text={`Players appear after ${lb.data.min_settled} settled prediction${lb.data.min_settled === 1 ? '' : 's'}.`}
        />
      )}
      {lb.data && lb.data.items.length > 0 && (
        <>
          {showPodium && <Podium rows={lb.data.items} metric={metric} />}
          <ol className="space-y-2">
            {listRows.map((r) => (
              <Row key={r.rank} r={r} metric={metric} />
            ))}
          </ol>
          {lb.data.me && !meInList && (
            <div className="mt-4">
              <p className="mb-1 px-1 text-xs text-slate-500">Your position</p>
              <ol>
                <Row r={lb.data.me} metric={metric} />
              </ol>
            </div>
          )}
        </>
      )}
    </>
  )
}