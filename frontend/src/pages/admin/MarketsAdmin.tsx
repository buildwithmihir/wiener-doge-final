import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError } from '../../lib/api'
import { ADMIN_DURATIONS, validTargetPrice } from '../../lib/admin'
import { dateTime, durationLabel, price } from '../../lib/format'
import type { AdminMarket } from '../../lib/types'
import { Badge, ErrorState, Spinner } from '../../components/ui'

function errText(e: unknown): string | null {
  if (!e) return null
  return e instanceof ApiError ? e.message : 'Request failed.'
}

const input =
  'w-full rounded-xl border border-white/15 bg-ink-900 px-3 py-2 text-sm text-white outline-none focus:border-neon-blue'

function CreateMarket({ symbols }: { symbols: string[] }) {
  const qc = useQueryClient()
  const [symbol, setSymbol] = useState(symbols[0] ?? 'SOL')
  const [duration, setDuration] = useState(86400)
  const [target, setTarget] = useState('')
  const [reason, setReason] = useState('')
  const create = useMutation({
    mutationFn: () =>
      api('/admin/markets', {
        method: 'POST',
        body: { symbol, duration_seconds: duration, target_price: target.trim(), reason: reason.trim(), publish: true },
      }),
    onSuccess: () => {
      setTarget('')
      setReason('')
      void qc.invalidateQueries({ queryKey: ['admin-markets'] })
      void qc.invalidateQueries({ queryKey: ['markets'] })
    },
  })
  const canSend = validTargetPrice(target) && reason.trim().length > 0 && !create.isPending
  return (
    <form
      className="glass-flat space-y-3 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (canSend) create.mutate()
      }}
    >
      <p className="text-sm font-semibold text-white">Create market</p>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-slate-400">
          Asset
          <select className={`${input} mt-1`} value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {symbols.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-400">
          Duration
          <select className={`${input} mt-1`} value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
            {ADMIN_DURATIONS.map((d) => (
              <option key={d.seconds} value={d.seconds}>
                {d.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block text-xs text-slate-400">
        Target price (USD)
        <input className={`${input} mt-1`} inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="e.g. 119.40" />
      </label>
      <label className="block text-xs text-slate-400">
        Reason (audited)
        <input className={`${input} mt-1`} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="e.g. daily SOL market" />
      </label>
      <button type="submit" className="btn-primary w-full" disabled={!canSend}>
        {create.isPending ? 'Creating…' : 'Create and publish'}
      </button>
      {create.isSuccess && <p className="text-xs text-up">Market created.</p>}
      {errText(create.error) && (
        <p role="alert" className="text-xs text-down">
          {errText(create.error)}
        </p>
      )}
    </form>
  )
}

function MarketRow({ m, canVoid }: { m: AdminMarket; canVoid: boolean }) {
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const [confirmVoid, setConfirmVoid] = useState(false)
  const act = useMutation({
    mutationFn: (action: 'pause' | 'resume' | 'void') =>
      api(`/admin/markets/${m.id}/${action}`, { method: 'POST', body: { reason: reason.trim() } }),
    onSuccess: () => {
      setReason('')
      setConfirmVoid(false)
      void qc.invalidateQueries({ queryKey: ['admin-markets'] })
      void qc.invalidateQueries({ queryKey: ['markets'] })
    },
  })
  const live = m.status === 'open' || m.status === 'paused' || m.status === 'closed'
  const has = reason.trim().length > 0
  return (
    <li className="glass-flat space-y-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold text-white">
          {m.symbol} {durationLabel(m.duration_seconds)} · target {price(m.target_price)}
        </p>
        <Badge tone={m.status === 'open' ? 'up' : m.status === 'voided' ? 'down' : 'neutral'}>{m.status}</Badge>
      </div>
      <p className="text-xs text-slate-400">
        Closes {dateTime(m.closes_at)} · price {price(m.last_price)} · feed {m.feed_ok ? 'ok' : 'NOT ok'}
        {m.paused_by_feed ? ' · auto-paused by feed' : ''}
        {m.admin_pause_reason ? ` · paused: ${m.admin_pause_reason}` : ''}
      </p>
      {live && (
        <>
          <input className={input} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)" aria-label="Reason" />
          <div className="flex gap-2">
            {m.status === 'open' && (
              <button type="button" className="btn-ghost flex-1" disabled={!has || act.isPending} onClick={() => act.mutate('pause')}>
                Pause
              </button>
            )}
            {m.status === 'paused' && (
              <button type="button" className="btn-ghost flex-1" disabled={!has || act.isPending} onClick={() => act.mutate('resume')}>
                Resume
              </button>
            )}
            {canVoid &&
              (confirmVoid ? (
                <button type="button" className="btn flex-1 bg-down text-white" disabled={!has || act.isPending} onClick={() => act.mutate('void')}>
                  Confirm: void and refund all
                </button>
              ) : (
                <button type="button" className="btn-ghost flex-1 text-down" disabled={!has} onClick={() => setConfirmVoid(true)}>
                  Void…
                </button>
              ))}
          </div>
        </>
      )}
      {errText(act.error) && (
        <p role="alert" className="text-xs text-down">
          {errText(act.error)}
        </p>
      )}
    </li>
  )
}

export default function MarketsAdmin({ isAdmin }: { isAdmin: boolean }) {
  const list = useQuery({ queryKey: ['admin-markets'], queryFn: () => api<{ items: AdminMarket[] }>('/admin/markets?limit=50') })
  const symbols = ['SOL', 'WIENER']
  return (
    <div className="space-y-3">
      {isAdmin && <CreateMarket symbols={symbols} />}
      {list.isPending && <Spinner />}
      {list.isError && <ErrorState message="Could not load markets." onRetry={() => void list.refetch()} />}
      {list.data && list.data.items.length === 0 && <p className="text-center text-sm text-slate-400">No markets yet.</p>}
      <ul className="space-y-3">
        {list.data?.items.map((m) => (
          <MarketRow key={m.id} m={m} canVoid={isAdmin} />
        ))}
      </ul>
    </div>
  )
}
