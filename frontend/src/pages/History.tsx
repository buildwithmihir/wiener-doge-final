import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, CheckCircle2, History as HistoryIcon, Percent, TrendingUp } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { countdown, dateTime, durationLabel, price, usd } from '../lib/format'
import { FILTERS, summarize, type HistoryFilter } from '../lib/history'
import { unitsToDemo } from '../lib/money'
import type { Prediction, PredictionStatus, Quote } from '../lib/types'
import { AssetIcon } from '../components/AssetIcon'
import { Button } from '../components/shadcn/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '../components/shadcn/sheet'
import { EmptyState, ErrorState, PageTitle, Spinner } from '../components/ui'

const PAGE = 20

function chipClass(active: boolean): string {
  return `shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition ${
    active ? 'bg-neon-blue/20 text-neon-blue ring-1 ring-neon-blue/60' : 'bg-white/5 text-slate-300 hover:text-white'
  }`
}

const STATUS_LABEL: Record<PredictionStatus, string> = {
  open: 'Live',
  won: 'Win',
  lost: 'Loss',
  refunded: 'Refund',
  cashed_out: 'Cashed out',
}

const STATUS_BADGE: Record<PredictionStatus, string> = {
  open: 'bg-[#c4153d]',
  won: 'bg-green-600',
  lost: 'bg-rose-600',
  refunded: 'bg-amber-600',
  cashed_out: 'bg-teal-600',
}

const SIDES = [
  { key: 'above', label: 'Above', Icon: ArrowUp, color: 'text-up' },
  { key: 'below', label: 'Below', Icon: ArrowDown, color: 'text-down' },
] as const

function DollarDot() {
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[11px] font-bold text-white" aria-hidden>
      $
    </span>
  )
}

function DataRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1 text-[15px]">
      <span className="text-slate-400">{label}</span>
      <span className="flex items-center gap-2 font-semibold">{children}</span>
    </div>
  )
}

function Brand() {
  return (
    <div className="my-4 flex items-center gap-3">
      <span className="h-px flex-1 bg-white/10" />
      <span className="font-display text-2xl font-extrabold italic tracking-tight text-white">WienerDoge</span>
      <span className="h-px flex-1 bg-white/10" />
    </div>
  )
}

/** Live bet: current price in the box (like a live score), winning / behind, and a cashout button. */
function LiveCard({ p, quote, onCashout }: { p: Prediction; quote?: Quote; onCashout: () => void }) {
  const secondsLeft = Math.max(0, Math.floor((Date.parse(p.closes_at) - Date.now()) / 1000))
  const winning = quote?.winning ?? null
  const boxTone = winning === null ? 'border-slate-500 text-slate-300' : winning ? 'border-up/70 text-up' : 'border-down/70 text-down'
  const canCash = !!quote?.available && !!quote.amount

  return (
    <li className="rounded-2xl border border-white/5 bg-[#1b2c38] p-4 text-slate-300 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <AssetIcon symbol={p.symbol} size={30} />
          <p className="truncate text-lg font-bold text-white">{p.symbol}</p>
        </div>
        <span className="num text-lg font-bold text-sky-400">{p.payout_multiplier}</span>
      </div>
      <p className="mt-2 text-slate-400">Price at close · {durationLabel(p.duration_seconds)} market</p>

      <div className="mt-3 flex items-center gap-2.5">
        <span className={`rounded-md px-2 py-0.5 text-sm font-bold text-white ${STATUS_BADGE.open}`}>Live</span>
        <span className="text-slate-300">Closes in {countdown(secondsLeft)}</span>
        {winning !== null && (
          <span className={`ml-auto text-xs font-bold ${winning ? 'text-up' : 'text-down'}`}>{winning ? 'Winning' : 'Behind'}</span>
        )}
      </div>

      <div className="mt-3 grid grid-cols-[1fr_auto] items-center gap-3">
        <div className="space-y-2">
          {SIDES.map(({ key, label, Icon, color }) => {
            const picked = p.direction === key
            return (
              <div key={key} className="flex min-w-0 items-center gap-2">
                <Icon className={`h-5 w-5 shrink-0 ${color}`} aria-hidden />
                <span className={`truncate text-lg ${picked ? 'font-bold text-white' : 'text-slate-400'}`}>
                  {label} {price(p.target_price)}
                </span>
                {picked && <span className="text-xs text-slate-300">◂</span>}
              </div>
            )
          })}
        </div>
        <div className={`flex min-w-[5.5rem] flex-col items-center justify-center rounded-xl border-2 px-3 py-2 ${boxTone}`}>
          <span className="text-[10px] font-semibold uppercase tracking-wider opacity-80">Now</span>
          <span className="num text-lg font-bold">{quote?.current_price ? price(quote.current_price) : '—'}</span>
        </div>
      </div>

      <Brand />

      <DataRow label="Stake">
        <span className="num text-white">{usd(p.stake)}</span>
        <DollarDot />
      </DataRow>
      <DataRow label="Payout">
        <span className="num text-white">{usd(p.potential_payout)}</span>
        <DollarDot />
      </DataRow>

      <Button
        type="button"
        variant="secondary"
        size="lg"
        className="mt-3 w-full bg-[#3d5565] hover:bg-[#476579]"
        disabled={!canCash}
        onClick={onCashout}
      >
        {canCash && quote?.amount ? (
          <>
            Cashout {usd(quote.amount)} <DollarDot />
          </>
        ) : (
          'Cashout unavailable'
        )}
      </Button>
      {quote && !quote.available && quote.message && <p className="mt-2 text-center text-[11px] text-slate-500">{quote.message}</p>}
    </li>
  )
}

/** Finished bet (won / lost / refunded / cashed out). */
function DoneCard({ p }: { p: Prediction }) {
  const settled = p.status === 'won' || p.status === 'lost'
  return (
    <li className="rounded-2xl border border-white/5 bg-[#1b2c38] p-4 text-slate-300 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <AssetIcon symbol={p.symbol} size={30} />
          <p className="truncate text-lg font-bold text-white">{p.symbol}</p>
        </div>
        <span className={`rounded-md px-2.5 py-0.5 text-sm font-bold text-white ${STATUS_BADGE[p.status]}`}>{STATUS_LABEL[p.status]}</span>
      </div>

      <p className="mt-3 text-slate-400">Price at close · {durationLabel(p.duration_seconds)} market</p>
      <p className="mt-3 text-slate-300">{dateTime(p.created_at)}</p>

      <div className="mt-3 space-y-2">
        {SIDES.map(({ key, label, Icon, color }) => {
          const picked = p.direction === key
          const won = p.market_result === key
          const hasResult = p.market_result === 'above' || p.market_result === 'below'
          return (
            <div key={key} className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <Icon className={`h-5 w-5 shrink-0 ${color}`} aria-hidden />
                <span className={`truncate text-lg ${picked ? 'font-bold text-white' : 'text-slate-400'}`}>
                  {label} {price(p.target_price)}
                </span>
                {picked && (
                  <span className="text-xs text-slate-300" aria-label="Your pick">
                    ◂
                  </span>
                )}
              </div>
              {hasResult && (
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border-2 text-base font-bold ${
                    won ? 'border-up text-up' : 'border-slate-600 text-slate-500'
                  }`}
                  aria-label={won ? 'Winning side' : 'Losing side'}
                >
                  {won ? '✓' : '✕'}
                </span>
              )}
            </div>
          )
        })}
      </div>

      <Brand />

      <DataRow label="Odds">
        <span className="num text-sky-400">{p.payout_multiplier}x</span>
      </DataRow>
      <DataRow label="Stake">
        <span className="num text-white">{usd(p.stake)}</span>
        <DollarDot />
      </DataRow>
      <DataRow label={p.status === 'cashed_out' ? 'Cashed out' : 'Payout'}>
        <span className={`num ${p.status === 'won' ? 'text-up' : p.status === 'cashed_out' ? 'text-teal-300' : 'text-slate-300'}`}>{usd(p.payout)}</span>
        <DollarDot />
      </DataRow>
      {settled && (
        <DataRow label="Final price">
          <span className="num text-white">{price(p.settle_price)}</span>
        </DataRow>
      )}
      {p.status === 'cashed_out' && <p className="mt-1 text-[11px] text-slate-500">Cashed-out bets do not count toward your wager.</p>}
    </li>
  )
}

function CashoutSheet({ p, quote, onClose }: { p: Prediction; quote: Quote | undefined; onClose: () => void }) {
  const qc = useQueryClient()
  const cash = useMutation({
    mutationFn: () =>
      api<Prediction>(`/predictions/${p.id}/cashout`, {
        method: 'POST',
        body: { expected_amount: quote?.amount?.demo },
      }),
    onSuccess: () => {
      for (const key of ['predictions', 'quotes', 'wallet', 'wager', 'profile', 'vip']) void qc.invalidateQueries({ queryKey: [key] })
    },
    onError: () => void qc.invalidateQueries({ queryKey: ['quotes'] }),
  })

  const amount = quote?.amount ? BigInt(quote.amount.units) : null
  const diff = amount !== null ? amount - BigInt(p.stake.units) : null
  const done = cash.data

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetTitle className="font-display text-lg font-bold text-white">Cash out</SheetTitle>
        <SheetDescription className="mb-4 text-xs text-muted-foreground">
          {p.symbol} {p.direction.toUpperCase()} {price(p.target_price)}. The value follows the live price.
        </SheetDescription>

        {done ? (
          <div className="py-4 text-center">
            <CheckCircle2 className="mx-auto h-12 w-12 animate-pop text-up" />
            <p className="mt-2 text-lg font-semibold text-white">Cashed out {usd(done.payout)}</p>
            <p className="mt-1 text-sm text-slate-400">Added to your balance.</p>
            <Button type="button" className="mt-5 w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <>
            <div className="rounded-xl border border-primary/30 bg-primary/10 p-3 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">Your stake</span>
                <span className="num font-semibold">{usd(p.stake)}</span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-slate-400">Cashout value</span>
                <span className="num font-semibold text-white">{quote?.amount ? usd(quote.amount) : '—'}</span>
              </div>
              {diff !== null && (
                <div className="mt-1 flex justify-between">
                  <span className="text-slate-400">{diff >= 0n ? 'Profit' : 'Loss'}</span>
                  <span className={`num font-semibold ${diff >= 0n ? 'text-up' : 'text-down'}`}>
                    {diff >= 0n ? '+' : '-'}
                    {usd(unitsToDemo(diff >= 0n ? diff : -diff))}
                  </span>
                </div>
              )}
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Winning bets cash out for more, losing bets for less. A cashed-out bet does not count toward your wager.
            </p>
            {cash.error && (
              <p role="alert" className="mt-3 text-sm text-down">
                {cash.error instanceof ApiError ? cash.error.message : 'Something went wrong. Try again.'}
              </p>
            )}
            <Button type="button" size="lg" className="mt-4 w-full" disabled={!quote?.available || cash.isPending} onClick={() => cash.mutate()}>
              {cash.isPending ? 'Cashing out…' : quote?.amount ? `Confirm cashout ${usd(quote.amount)}` : 'Cashout unavailable'}
            </Button>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

export default function HistoryPage() {
  const [filter, setFilter] = useState<HistoryFilter>('all')
  const [cashingId, setCashingId] = useState<string | null>(null)

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

  const quotes = useQuery({
    queryKey: ['quotes'],
    queryFn: () => api<{ items: Quote[] }>('/predictions/quotes'),
    refetchInterval: 10_000,
    enabled: filter === 'all' || filter === 'open',
  })
  const quoteById = useMemo(() => new Map((quotes.data?.items ?? []).map((q) => [q.prediction_id, q])), [quotes.data])

  const items = useMemo(() => query.data?.pages.flat() ?? [], [query.data])
  const summary = useMemo(() => summarize(items), [items])
  const cashing = cashingId ? items.find((p) => p.id === cashingId) : undefined

  return (
    <>
      <PageTitle icon={HistoryIcon} tone="violet" title="History" subtitle="Your predictions." />

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
        <EmptyState icon={HistoryIcon} tone="violet" title="No predictions yet" text="Place a prediction on the Markets tab and it will show up here." />
      )}

      {items.length > 0 && (
        <>
          <div className="mb-3 grid grid-cols-3 gap-2">
            <div className="glass-flat p-3 text-center">
              <CheckCircle2 className="mx-auto h-4 w-4 text-sky-400" aria-hidden />
              <p className="mt-1 text-[11px] text-slate-500">Settled</p>
              <p className="num text-lg font-semibold">{summary.settled}</p>
            </div>
            <div className="glass-flat p-3 text-center">
              <Percent className="mx-auto h-4 w-4 text-violet-400" aria-hidden />
              <p className="mt-1 text-[11px] text-slate-500">Win rate</p>
              <p className="num text-lg font-semibold">{summary.winRatePct === '—' ? '—' : `${summary.winRatePct}%`}</p>
            </div>
            <div className="glass-flat p-3 text-center">
              <TrendingUp className="mx-auto h-4 w-4 text-emerald-400" aria-hidden />
              <p className="mt-1 text-[11px] text-slate-500">Net (loaded)</p>
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
            {items.map((p) =>
              p.status === 'open' ? (
                <LiveCard key={p.id} p={p} quote={quoteById.get(p.id)} onCashout={() => setCashingId(p.id)} />
              ) : (
                <DoneCard key={p.id} p={p} />
              ),
            )}
          </ul>
          {query.hasNextPage && (
            <button type="button" className="btn-ghost mt-4 w-full" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
              {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
            </button>
          )}
        </>
      )}

      {cashing && <CashoutSheet p={cashing} quote={quoteById.get(cashing.id)} onClose={() => setCashingId(null)} />}
    </>
  )
}