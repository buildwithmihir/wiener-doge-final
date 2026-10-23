import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, newIdempotencyKey, ApiError } from '../../lib/api'
import { checkCreditAmount } from '../../lib/admin'
import { dateTime, usd } from '../../lib/format'
import type { AdminUserInfo } from '../../lib/types'
import { Badge } from '../../components/ui'

const input =
  'w-full rounded-xl border border-white/15 bg-ink-900 px-3 py-2 text-sm text-white outline-none focus:border-neon-blue'

function errText(e: unknown): string | null {
  if (!e) return null
  return e instanceof ApiError ? e.message : 'Request failed.'
}

function UserCard({ user, onChanged }: { user: AdminUserInfo; onChanged: () => void }) {
  const qc = useQueryClient()
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const key = useRef(newIdempotencyKey())
  const checked = checkCreditAmount(amount)
  const has = reason.trim().length > 0

  const credit = useMutation({
    mutationFn: () =>
      api(`/admin/users/${user.id}/credits`, {
        method: 'POST',
        headers: { 'Idempotency-Key': key.current },
        body: { amount: checked.ok ? checked.text : '0', reason: reason.trim() },
      }),
    onSuccess: () => {
      key.current = newIdempotencyKey()      // a new adjustment gets a new key; a retry of this one reuses it
      setAmount('')
      setReason('')
      onChanged()
      void qc.invalidateQueries({ queryKey: ['wallet'] })
    },
  })
  const status = useMutation({
    mutationFn: (next: 'active' | 'suspended' | 'banned') =>
      api(`/admin/users/${user.id}/status`, { method: 'POST', body: { status: next, reason: reason.trim() } }),
    onSuccess: () => {
      setReason('')
      onChanged()
    },
  })

  return (
    <div className="glass-flat space-y-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-white">{user.display_name}</p>
          <p className="text-xs text-slate-400">
            tg {user.telegram_id}
            {user.username ? ` · @${user.username}` : ''} · seen {user.last_seen_at ? dateTime(user.last_seen_at) : 'never'}
          </p>
        </div>
        <Badge tone={user.status === 'active' ? 'up' : 'down'}>{user.status}</Badge>
      </div>
      <p className="text-sm text-slate-300">
        Available <span className="num font-semibold text-white">{usd(user.wallet.available)}</span> · total{' '}
        <span className="num">{usd(user.wallet.total)}</span> (demo credits)
      </p>
      <input className={input} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required, audited)" aria-label="Reason" />
      <div className="flex gap-2">
        <input className={input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Credits, e.g. 50 or -12.5" aria-label="Amount" />
        <button type="button" className="btn-primary" disabled={!checked.ok || !has || credit.isPending} onClick={() => credit.mutate()}>
          Apply
        </button>
      </div>
      {amount && !checked.ok && <p className="text-xs text-down">{checked.error}</p>}
      <div className="flex gap-2">
        {(['active', 'suspended', 'banned'] as const)
          .filter((s) => s !== user.status)
          .map((s) => (
            <button key={s} type="button" className="btn-ghost flex-1 capitalize" disabled={!has || status.isPending} onClick={() => status.mutate(s)}>
              Set {s}
            </button>
          ))}
      </div>
      {credit.isSuccess && <p className="text-xs text-up">Credits updated.</p>}
      {(errText(credit.error) || errText(status.error)) && (
        <p role="alert" className="text-xs text-down">
          {errText(credit.error) ?? errText(status.error)}
        </p>
      )}
    </div>
  )
}

export default function UsersAdmin() {
  const [tg, setTg] = useState('')
  const [user, setUser] = useState<AdminUserInfo | null>(null)
  const find = useMutation({
    mutationFn: (id: string) => api<AdminUserInfo>(`/admin/users/lookup?telegram_id=${encodeURIComponent(id)}`),
    onSuccess: setUser,
    onError: () => setUser(null),
  })
  const valid = /^\d{1,13}$/.test(tg.trim()) && tg.trim() !== '0'
  return (
    <div className="space-y-3">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (valid) find.mutate(tg.trim())
        }}
      >
        <input className={input} inputMode="numeric" value={tg} onChange={(e) => setTg(e.target.value)} placeholder="Telegram numeric id" aria-label="Telegram id" />
        <button type="submit" className="btn-ghost" disabled={!valid || find.isPending}>
          Find
        </button>
      </form>
      {errText(find.error) && (
        <p role="alert" className="text-sm text-down">
          {errText(find.error)}
        </p>
      )}
      {user && <UserCard key={user.id} user={user} onChanged={() => find.mutate(String(user.telegram_id))} />}
    </div>
  )
}
