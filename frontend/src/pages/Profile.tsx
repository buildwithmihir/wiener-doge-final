import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, User as UserIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { dateTime, usd } from '../lib/format'
import type { NotificationPrefs, ProfileResponse, Wallet } from '../lib/types'
import { useSession } from '../auth/AuthContext'
import { Badge, ErrorState, PageTitle, Spinner } from '../components/ui'

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass-flat p-3 text-center">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="num mt-1 text-lg font-semibold">{value}</p>
    </div>
  )
}

function ReferralApply() {
  const qc = useQueryClient()
  const [code, setCode] = useState('')
  const apply = useMutation({
    mutationFn: () => api('/referrals/apply', { method: 'POST', body: { code: code.trim() } }),
    onSuccess: () => {
      setCode('')
      void qc.invalidateQueries({ queryKey: ['profile'] })
    },
  })
  const message = apply.error instanceof ApiError ? apply.error.message : apply.error ? 'Could not apply the code.' : null
  return (
    <form
      className="mt-3 space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (code.trim()) apply.mutate()
      }}
    >
      <label htmlFor="ref-code" className="text-xs text-slate-400">
        Have a friend's code? (only before your first prediction)
      </label>
      <div className="flex gap-2">
        <input
          id="ref-code"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          maxLength={16}
          autoCapitalize="characters"
          autoComplete="off"
          className="min-w-0 flex-1 rounded-xl border border-white/15 bg-ink-900 px-3 py-2 text-sm uppercase tracking-widest text-white outline-none focus:border-neon-blue"
          placeholder="CODE"
        />
        <button type="submit" className="btn-ghost" disabled={apply.isPending || !code.trim()}>
          Apply
        </button>
      </div>
      {message && (
        <p role="alert" className="text-xs text-down">
          {message}
        </p>
      )}
    </form>
  )
}

function Privacy({ data }: { data: ProfileResponse['privacy'] }) {
  const qc = useQueryClient()
  const [alias, setAlias] = useState(data.leaderboard_alias ?? '')
  const save = useMutation({
    mutationFn: (body: { leaderboard_alias?: string | null; hide_on_leaderboard?: boolean }) =>
      api('/profile', { method: 'PATCH', body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['profile'] }),
  })
  const message = save.error instanceof ApiError ? save.error.message : save.error ? 'Could not save.' : null
  return (
    <div className="glass-flat space-y-3 p-4">
      <p className="text-sm font-semibold text-white">Leaderboard privacy</p>
      <label className="flex items-center justify-between gap-3 text-sm text-slate-300">
        <span>Hide me from the leaderboard</span>
        <input
          type="checkbox"
          className="h-5 w-5 accent-[#4f8cff]"
          checked={data.hide_on_leaderboard}
          disabled={save.isPending}
          onChange={(e) => save.mutate({ hide_on_leaderboard: e.target.checked })}
        />
      </label>
      <div>
        <label htmlFor="alias" className="text-xs text-slate-400">
          Public alias (blank = your first name)
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id="alias"
            value={alias}
            maxLength={32}
            onChange={(e) => setAlias(e.target.value)}
            className="min-w-0 flex-1 rounded-xl border border-white/15 bg-ink-900 px-3 py-2 text-sm text-white outline-none focus:border-neon-blue"
          />
          <button type="button" className="btn-ghost" disabled={save.isPending} onClick={() => save.mutate({ leaderboard_alias: alias.trim() || null })}>
            Save
          </button>
        </div>
      </div>
      {message && (
        <p role="alert" className="text-xs text-down">
          {message}
        </p>
      )}
    </div>
  )
}

const PREF_LABELS: { key: keyof NotificationPrefs; label: string }[] = [
  { key: 'market_results', label: 'Market results (won / lost / refunded)' },
  { key: 'referrals', label: 'Referral rewards' },
  { key: 'vip', label: 'VIP tier unlocks' },
]

function NotificationSettings() {
  const qc = useQueryClient()
  const prefs = useQuery({ queryKey: ['notification-prefs'], queryFn: () => api<NotificationPrefs>('/notifications/preferences') })
  const save = useMutation({
    mutationFn: (body: Partial<NotificationPrefs>) => api<NotificationPrefs>('/notifications/preferences', { method: 'PATCH', body }),
    onSuccess: (data) => qc.setQueryData(['notification-prefs'], data),
  })
  if (prefs.isPending) return null
  if (prefs.isError || !prefs.data) return null
  const data = prefs.data
  return (
    <div className="glass-flat space-y-3 p-4">
      <p className="text-sm font-semibold text-white">Telegram messages</p>
      {PREF_LABELS.map(({ key, label }) => (
        <label key={key} className="flex items-center justify-between gap-3 text-sm text-slate-300">
          <span>{label}</span>
          <input
            type="checkbox"
            className="h-5 w-5 accent-[#4f8cff]"
            checked={data[key]}
            disabled={save.isPending}
            onChange={(e) => save.mutate({ [key]: e.target.checked })}
          />
        </label>
      ))}
      <p className="text-xs text-slate-500">Sent by the bot.</p>
      {save.isError && (
        <p role="alert" className="text-xs text-down">
          Could not save.
        </p>
      )}
    </div>
  )
}

export default function ProfilePage() {
  const profile = useQuery({ queryKey: ['profile'], queryFn: () => api<ProfileResponse>('/profile') })
  const wallet = useQuery({ queryKey: ['wallet'], queryFn: () => api<Wallet>('/wallet') })
  const { user } = useSession()
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  return (
    <>
      <PageTitle icon={UserIcon} title="Profile" subtitle="Your account" />
      {profile.isPending && <Spinner />}
      {profile.isError && <ErrorState message="Could not load your profile." onRetry={() => void profile.refetch()} />}
      {profile.data && (
        <div className="space-y-3">
          <div className="glass p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-xl font-bold text-white">{profile.data.user.display_name}</p>
                {profile.data.user.username && <p className="text-sm text-slate-400">@{profile.data.user.username}</p>}
                <p className="mt-1 text-xs text-slate-500">Member since {dateTime(profile.data.user.member_since)}</p>
              </div>
              <Badge tone="demo">{profile.data.vip.current?.name ?? 'No tier'}</Badge>
            </div>
            {wallet.data && (
              <Link to="/wallet" className="mt-4 flex items-center justify-between rounded-xl bg-white/5 px-3 py-2 text-sm">
                <span className="text-slate-400">Balance</span>
                <span className="num font-semibold text-white">{usd(wallet.data.available)}</span>
              </Link>
            )}
          </div>

          <div className="grid grid-cols-3 gap-2">
            <Stat label="Settled" value={String(profile.data.stats.settled)} />
            <Stat label="Accuracy" value={profile.data.stats.accuracy_pct === null ? '—' : `${profile.data.stats.accuracy_pct}%`} />
            <Stat label="Staked" value={usd(profile.data.stats.staked)} />
          </div>

          <div className="glass-flat p-4">
            <p className="text-sm font-semibold text-white">Invite friends</p>
            <p className="mt-1 text-xs text-slate-400">
              You get {usd(profile.data.referral.reward_per_referral)} as a bonus when a friend joins with your code and places a prediction.
            </p>
            <div className="mt-3 flex items-center justify-between rounded-xl border border-dashed border-neon-blue/40 bg-ink-900 px-3 py-2">
              <span className="num text-lg font-bold tracking-widest text-white">{profile.data.referral.code}</span>
              <button
                type="button"
                className="btn-ghost px-3 py-1.5"
                aria-label="Copy referral code"
                onClick={() => void copyText(profile.data.referral.code).then((ok) => setCopied(ok ? 'yes' : 'no'))}
              >
                <Copy className="h-4 w-4" aria-hidden />
                {copied === 'yes' ? 'Copied' : copied === 'no' ? 'Copy failed' : 'Copy'}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-400">
              {profile.data.referral.total} invited · {profile.data.referral.rewarded} rewarded · {profile.data.referral.pending} pending · earned{' '}
              {usd(profile.data.referral.earned)}
            </p>
            {!profile.data.referral.already_referred && <ReferralApply />}
          </div>

          <NotificationSettings />

          <Privacy key={profile.data.privacy.leaderboard_alias ?? ''} data={profile.data.privacy} />

          <Link to="/leaderboard" className="btn-ghost w-full">
            View leaderboard
          </Link>
          <Link to="/vip" className="btn-ghost w-full">
            View VIP tiers
          </Link>
          {(user.is_admin || user.roles.includes('moderator')) && (
            <Link to="/admin" className="btn-ghost w-full">
              Admin panel
            </Link>
          )}
        </div>
      )}
    </>
  )
}
