import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError } from '../../lib/api'
import { dateTime, usd } from '../../lib/format'
import type { AdminWithdrawal } from '../../lib/types'
import { Badge, ErrorState, Spinner } from '../../components/ui'

const STATUSES = ['pending', 'approved', 'sending', 'failed', 'sent', 'rejected'] as const
type Status = (typeof STATUSES)[number]

const input =
  'w-full rounded-xl border border-white/15 bg-ink-900 px-3 py-2 text-sm text-white outline-none focus:border-neon-blue'

function errText(e: unknown): string | null {
  if (!e) return null
  return e instanceof ApiError ? e.message : 'Request failed.'
}

function chipClass(active: boolean): string {
  return `shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition ${
    active ? 'bg-neon-blue/20 text-neon-blue ring-1 ring-neon-blue/60' : 'bg-white/5 text-slate-300 hover:text-white'
  }`
}

/** One list per status. Same key = one shared request, so tabs and counters never double-fetch. */
function useWithdrawals(status: Status) {
  return useQuery({
    queryKey: ['admin-withdrawals', 'list', status],
    queryFn: () => api<{ items: AdminWithdrawal[] }>(`/admin/withdrawals?status=${status}`),
    refetchInterval: 20_000,
  })
}

function Row({ w }: { w: AdminWithdrawal }) {
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const [confirmApprove, setConfirmApprove] = useState(false)
  const act = useMutation({
    mutationFn: (action: 'approve' | 'reject') =>
      api(`/admin/withdrawals/${w.id}/${action}`, { method: 'POST', body: { reason: reason.trim() } }),
    onSuccess: () => {
      setReason('')
      setConfirmApprove(false)
      void qc.invalidateQueries({ queryKey: ['admin-withdrawals'] })
    },
    onError: () => setConfirmApprove(false),
  })
  const has = reason.trim().length > 0
  const canApprove = w.status === 'pending' || w.status === 'failed'
  const canReject = canApprove || w.status === 'approved'
  const tone = w.status === 'sent' ? 'up' : w.status === 'rejected' || w.status === 'failed' ? 'down' : 'neutral'

  return (
    <li className="glass-flat space-y-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold text-white">
          {usd(w.amount)} <span className="text-slate-400">as {w.asset}</span>
        </p>
        <Badge tone={tone}>{w.status}</Badge>
      </div>
      <p className="break-all font-mono text-xs text-slate-300">{w.address}</p>
      <p className="text-xs text-slate-400">
        user {w.user_id.slice(0, 8)} · {dateTime(w.created_at)}
        {w.native_amount ? ` · ${w.native_amount} ${w.asset}` : ''}
      </p>
      {w.note && <p className="text-xs text-slate-300">Note: {w.note}</p>}
      {w.status === 'approved' && (
        <p className="rounded-lg bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
          Approved and waiting to be sent. If it stays here for more than a few minutes, check the payments cron job and the hot wallet balance.
        </p>
      )}
      {w.tx_signature && (
        <a className="block text-xs text-neon-blue underline" href={`https://solscan.io/tx/${w.tx_signature}`} target="_blank" rel="noreferrer">
          View transaction
        </a>
      )}

      {canReject && !confirmApprove && (
        <>
          <input className={input} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)" aria-label="Reason" />
          <div className="flex gap-2">
            {canApprove && (
              <button type="button" className="btn-primary flex-1" disabled={!has || act.isPending} onClick={() => setConfirmApprove(true)}>
                Approve…
              </button>
            )}
            <button type="button" className="btn-ghost flex-1 text-down" disabled={!has || act.isPending} onClick={() => act.mutate('reject')}>
              Reject and refund
            </button>
          </div>
        </>
      )}

      {canApprove && confirmApprove && (
        <div className="space-y-2 rounded-xl border border-up/40 bg-up/10 p-3">
          <p className="text-sm font-semibold text-white">Send {usd(w.amount)} as {w.asset}?</p>
          <p className="break-all font-mono text-xs text-slate-200">{w.address}</p>
          <p className="text-xs text-slate-300">Blockchain transfers cannot be undone. Reason: {reason.trim()}</p>
          <div className="flex gap-2">
            <button type="button" className="btn-ghost flex-1" disabled={act.isPending} onClick={() => setConfirmApprove(false)}>
              Cancel
            </button>
            <button type="button" className="btn-primary flex-1" disabled={act.isPending} onClick={() => act.mutate('approve')}>
              {act.isPending ? 'Approving…' : 'Yes, approve and send'}
            </button>
          </div>
        </div>
      )}

      {errText(act.error) && (
        <p role="alert" className="text-xs text-down">
          {errText(act.error)}
        </p>
      )}
    </li>
  )
}

export default function WithdrawalsAdmin() {
  const [status, setStatus] = useState<Status>('pending')
  const list = useWithdrawals(status)
  const pending = useWithdrawals('pending')
  const approved = useWithdrawals('approved')

  const counts: Partial<Record<Status, number>> = {
    pending: pending.data?.items.length,
    approved: approved.data?.items.length,
  }
  const approvedCount = counts.approved ?? 0

  return (
    <div className="space-y-3">
      <p className="px-1 text-xs text-slate-400">
        Check the address and the user's history before approving. The token amount is calculated from the market price at the moment it is sent.
      </p>

      {approvedCount > 0 && status !== 'approved' && (
        <button
          type="button"
          className="w-full rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-left text-xs text-amber-200"
          onClick={() => setStatus('approved')}
        >
          {approvedCount} approved withdrawal{approvedCount === 1 ? ' is' : 's are'} waiting to be sent. Tap to review.
        </button>
      )}

      <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Withdrawal status">
        {STATUSES.map((s) => {
          const n = counts[s]
          return (
            <button key={s} type="button" role="tab" aria-selected={status === s} className={`${chipClass(status === s)} capitalize`} onClick={() => setStatus(s)}>
              {s}
              {n ? ` (${n})` : ''}
            </button>
          )
        })}
      </div>

      {list.isPending && <Spinner />}
      {list.isError && <ErrorState message="Could not load withdrawals." onRetry={() => void list.refetch()} />}
      {list.data && list.data.items.length === 0 && <p className="text-center text-sm text-slate-400">Nothing here.</p>}
      <ul className="space-y-3">
        {list.data?.items.map((w) => (
          <Row key={w.id} w={w} />
        ))}
      </ul>
    </div>
  )
}



