import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BookOpen,
  CheckCircle2,
  Coins,
  Copy,
  History as HistoryIcon,
  LifeBuoy,
  Percent,
  Radio,
  Star,
  Trophy,
  User as UserIcon,
  Wallet as WalletIcon,
  type LucideIcon,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { dateTime, usd } from '../lib/format'
import { HELP_URL, SUPPORT_URL } from '../lib/links'
import type { NotificationPrefs, ProfileResponse, Wallet } from '../lib/types'
import { useSession } from '../auth/AuthContext'
import { ErrorState, PageTitle, Spinner } from '../components/ui'
import { WagerCard } from '../components/WagerCard'

const TIER_RING: Record<string, string> = {
  Bronze: 'from-[#8a4b1f] via-[#c46d2f] to-[#f0a15f]',
  Silver: 'from-[#5b6477] via-[#a9b2c6] to-[#eef1f8]',
  Gold: 'from-[#b8791a] via-[#f5b942] to-[#ffe08a]',
  Platinum: 'from-[#0e7490] via-[#22d3ee] to-[#e0f2fe]',
}
const NO_TIER_RING = 'from-slate-600 to-slate-400'

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const letters = parts.length >= 2 ? `${parts[0]![0]}${parts[1]![0]}` : (parts[0] ?? '?').slice(0, 2)
  return letters.toUpperCase()
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{title}</h2>
      {children}
    </section>
  )
}

function Stat({ icon: Icon, tone, label, value }: { icon: LucideIcon; tone: string; label: string; value: string }) {
  return (
    <div className="glass-flat flex items-center gap-3 p-3">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tone}`}>
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-[11px] text-slate-500">{label}</p>
        <p className="num truncate text-lg font-bold text-white">{value}</p>
      </div>
    </div>
  )
}

function QuickLink({ to, icon: Icon, label, color }: { to: string; icon: LucideIcon; label: string; color: string }) {
  return (
    <Link to={to} className="glass-flat flex flex-col items-center gap-1.5 p-3 text-center transition active:scale-95">
      <Icon className={`h-5 w-5 ${color}`} aria-hidden />
      <span className="text-[11px] font-semibold text-slate-200">{label}</span>
    </Link>
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
    mutationFn: (body: { leaderboard_alias?: string | null; hide_on_leaderboard?: boolean }) => api('/profile', { method: 'PATCH', body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['profile'] }),
  })
  const message = save.error instanceof ApiError ? save.error.message : save.error ? 'Could not save.' : null
  return (
    <div className="glass-flat space-y-3 p-4">
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
  { key: 'market_results', label: 'Winning bets' },
  { key: 'payments', label: 'Deposits and withdrawals' },
  { key: 'raffles', label: 'New raffles and announcements' },
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
  if (prefs.isPending || prefs.isError || !prefs.data) return null
  const data = prefs.data
  return (
    <div className="glass-flat space-y-3 p-4">
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
      <p className="text-xs text-slate-500">Shown in the bell and sent by the bot.</p>
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
      <PageTitle icon={UserIcon} title="Profile" subtitle="Your account and stats" />
      {profile.isPending && <Spinner />}
      {profile.isError && <ErrorState message="Could not load your profile." onRetry={() => void profile.refetch()} />}
      {profile.data && (
        <div className="space-y-5">
          {/* identity card */}
          <div className="glass p-5">
            <div className="flex items-center gap-4">
              <span
                className={`flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full bg-gradient-to-br p-[3px] ${
                  TIER_RING[profile.data.vip.current?.name ?? ''] ?? NO_TIER_RING
                }`}
              >
                <span className="font-display flex h-full w-full items-center justify-center rounded-full bg-card text-2xl font-extrabold text-white">
                  {initials(profile.data.user.display_name)}
                </span>
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xl font-bold text-white">{profile.data.user.display_name}</p>
                {profile.data.user.username && <p className="truncate text-sm text-slate-400">@{profile.data.user.username}</p>}
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full border border-gold/40 bg-gold/10 px-2.5 py-0.5 text-xs font-semibold text-gold">
                    <Star className="h-3 w-3" aria-hidden /> {profile.data.vip.current?.name ?? 'No tier yet'}
                  </span>
                  <span className="text-[11px] text-slate-500">Since {dateTime(profile.data.user.member_since)}</span>
                </div>
              </div>
            </div>
            {wallet.data && (
              <Link to="/wallet" className="mt-4 flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                <span className="text-sm text-slate-400">Available balance</span>
                <span className="num text-lg font-bold text-white">{usd(wallet.data.available)}</span>
              </Link>
            )}
          </div>

          {/* shortcuts */}
          <div className="grid grid-cols-4 gap-2">
            <QuickLink to="/wallet" icon={WalletIcon} label="Wallet" color="text-emerald-400" />
            <QuickLink to="/history" icon={HistoryIcon} label="Bets" color="text-violet-400" />
            <QuickLink to="/vip" icon={Star} label="VIP" color="text-amber-400" />
            <QuickLink to="/leaderboard" icon={Trophy} label="Ranks" color="text-sky-400" />
          </div>

          {/* stats */}
          <Section title="Performance">
            <div className="grid grid-cols-2 gap-2">
              <Stat icon={Radio} tone="bg-sky-400/15 text-sky-300" label="Live bets" value={String(profile.data.stats.open)} />
              <Stat icon={CheckCircle2} tone="bg-emerald-400/15 text-emerald-300" label="Settled" value={String(profile.data.stats.settled)} />
              <Stat
                icon={Percent}
                tone="bg-violet-400/15 text-violet-300"
                label="Accuracy"
                value={profile.data.stats.accuracy_pct === null ? '—' : `${profile.data.stats.accuracy_pct}%`}
              />
              <Stat icon={Coins} tone="bg-amber-400/15 text-amber-300" label="Wagered (settled)" value={usd(profile.data.stats.staked)} />
            </div>
          </Section>

          <Section title="Withdrawal requirement">
            <WagerCard />
          </Section>

          {/* referrals */}
          <Section title="Invite friends">
            <div className="glass-flat p-4">
              <p className="text-xs text-slate-400">
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
              <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                {[
                  ['Invited', String(profile.data.referral.total)],
                  ['Rewarded', String(profile.data.referral.rewarded)],
                  ['Pending', String(profile.data.referral.pending)],
                  ['Earned', usd(profile.data.referral.earned)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl bg-black/25 px-1 py-2">
                    <p className="text-[10px] text-slate-500">{label}</p>
                    <p className="num text-sm font-semibold text-white">{value}</p>
                  </div>
                ))}
              </div>
              {!profile.data.referral.already_referred && <ReferralApply />}
            </div>
          </Section>

          <Section title="Notifications">
            <NotificationSettings />
          </Section>

          <Section title="Leaderboard privacy">
            <Privacy key={profile.data.privacy.leaderboard_alias ?? ''} data={profile.data.privacy} />
          </Section>

          <Section title="Help">
            <div className="grid grid-cols-2 gap-2">
              <a href={HELP_URL} target="_blank" rel="noreferrer" className="btn-ghost">
                <BookOpen className="h-4 w-4 text-emerald-300" aria-hidden /> Help guide
              </a>
              <a href={SUPPORT_URL} target="_blank" rel="noreferrer" className="btn-ghost">
                <LifeBuoy className="h-4 w-4 text-cyan-300" aria-hidden /> Support
              </a>
            </div>
          </Section>

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