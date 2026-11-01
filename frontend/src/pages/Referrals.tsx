import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Clock, Coins, Copy, Gift, Share2, Target, UserPlus, Users, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { api, ApiError } from '../lib/api'
import { usd } from '../lib/format'
import type { ReferralInfo } from '../lib/types'
import { Badge, ErrorState, IconTile, PageTitle, Spinner, type IconTone } from '../components/ui'
import { Progress } from '../components/shadcn/progress'

const BOT_URL = (import.meta.env.VITE_BOT_URL as string | undefined) || ''

function ReferralApply() {
  const qc = useQueryClient()
  const [code, setCode] = useState('')
  const apply = useMutation({
    mutationFn: () => api('/referrals/apply', { method: 'POST', body: { code: code.trim() } }),
    onSuccess: () => {
      setCode('')
      void qc.invalidateQueries({ queryKey: ['referrals'] })
      void qc.invalidateQueries({ queryKey: ['profile'] })
    },
  })
  const message = apply.error instanceof ApiError ? apply.error.message : apply.error ? 'Could not apply the code.' : null
  return (
    <form
      className="glass-flat space-y-2 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (code.trim()) apply.mutate()
      }}
    >
      <label htmlFor="ref-code" className="text-sm font-semibold text-white">
        Have a friend's code?
      </label>
      <p className="text-xs text-slate-400">You can add one only before your first prediction.</p>
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

function Step({ icon, tone, title, text }: { icon: LucideIcon; tone: IconTone; title: string; text: string }) {
  return (
    <li className="flex items-center gap-3">
      <IconTile icon={icon} tone={tone} />
      <div className="min-w-0">
        <p className="text-sm font-semibold text-white">{title}</p>
        <p className="text-xs text-slate-400">{text}</p>
      </div>
    </li>
  )
}

function Stat({ icon: Icon, tone, label, value }: { icon: LucideIcon; tone: string; label: string; value: string }) {
  return (
    <div className="glass-flat p-3 text-center">
      <span className={`mx-auto flex h-9 w-9 items-center justify-center rounded-xl ${tone}`}>
        <Icon className="h-[18px] w-[18px]" aria-hidden />
      </span>
      <p className="mt-1.5 text-[11px] text-slate-500">{label}</p>
      <p className="num text-base font-bold text-white">{value}</p>
    </div>
  )
}

export default function ReferralsPage() {
  const ref = useQuery({ queryKey: ['referrals'], queryFn: () => api<ReferralInfo>('/referrals') })
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied('yes')
    } catch {
      setCopied('no')
    }
  }

  const share = (r: ReferralInfo) => {
    const text = `Join me on WienerDoge Prediction Market! Use my invite code ${r.code} when you sign up.`
    const link = BOT_URL || window.location.origin
    window.open(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`, '_blank')
  }

  return (
    <>
      <PageTitle icon={Gift} tone="pink" title="Invite friends" subtitle="Earn a bonus for every friend who plays." />
      {ref.isPending && <Spinner />}
      {ref.isError && <ErrorState message="Could not load your referrals." onRetry={() => void ref.refetch()} />}
      {ref.data && (
        <div className="space-y-4">
          {/* hero + code */}
          <section className="glass space-y-4 p-5">
            <div className="text-center">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">You earn</p>
              <p className="font-display text-4xl font-extrabold text-gold">{usd(ref.data.reward_per_referral)}</p>
              <p className="mt-1 text-sm text-slate-300">per friend who wagers {usd(ref.data.min_wager)}</p>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-dashed border-neon-blue/40 bg-ink-900 px-3 py-2.5">
              <span className="num text-xl font-bold tracking-widest text-white">{ref.data.code}</span>
              <button type="button" className="btn-ghost px-3 py-1.5" aria-label="Copy referral code" onClick={() => void copy(ref.data.code)}>
                <Copy className="h-4 w-4" aria-hidden />
                {copied === 'yes' ? 'Copied' : copied === 'no' ? 'Copy failed' : 'Copy'}
              </button>
            </div>
            <button type="button" className="btn-primary w-full" onClick={() => share(ref.data)}>
              <Share2 className="h-4 w-4" aria-hidden /> Share on Telegram
            </button>
          </section>

          {/* how it works */}
          <section className="space-y-2">
            <h2 className="px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">How it works</h2>
            <ul className="glass-flat space-y-3.5 p-4">
              <Step icon={Share2} tone="blue" title="Share your code" text="Send it to a friend before they place their first prediction." />
              <Step icon={UserPlus} tone="violet" title="Friend joins" text="They enter your code in the Invite friends screen." />
              <Step icon={Target} tone="orange" title={`Friend wagers ${usd(ref.data.min_wager)}`} text="Only settled bets count. Open and cashed-out bets do not." />
              <Step icon={Coins} tone="gold" title={`You get ${usd(ref.data.reward_per_referral)}`} text="Paid automatically to your balance." />
            </ul>
          </section>

          {/* stats */}
          <div className="grid grid-cols-3 gap-2">
            <Stat icon={Users} tone="bg-sky-400/15 text-sky-300" label="Invited" value={String(ref.data.total)} />
            <Stat icon={CheckCircle2} tone="bg-emerald-400/15 text-emerald-300" label="Rewarded" value={String(ref.data.rewarded)} />
            <Stat icon={Coins} tone="bg-amber-400/15 text-amber-300" label="Earned" value={usd(ref.data.earned)} />
          </div>

          {/* friends */}
          <section className="space-y-2">
            <h2 className="px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Your friends</h2>
            {ref.data.friends.length === 0 && (
              <p className="glass-flat p-4 text-center text-sm text-slate-400">No one has joined with your code yet.</p>
            )}
            <ul className="space-y-2">
              {ref.data.friends.map((f, i) => (
                <li key={`${f.name}-${i}`} className="glass-flat space-y-2 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate font-semibold text-white">{f.name || 'Friend'}</p>
                    {f.status === 'rewarded' ? (
                      <Badge tone="up">Rewarded</Badge>
                    ) : f.status === 'rejected' ? (
                      <Badge tone="down">Not eligible</Badge>
                    ) : (
                      <Badge>
                        <Clock className="h-3 w-3" aria-hidden /> In progress
                      </Badge>
                    )}
                  </div>
                  <Progress value={f.pct} aria-label={`${f.name} wager progress`} className="h-1.5 bg-black/40" />
                  <p className="num text-xs text-slate-400">
                    {usd(f.wagered)} of {usd(ref.data.min_wager)} wagered
                  </p>
                </li>
              ))}
            </ul>
          </section>

          {ref.data.already_referred ? (
            <p className="glass-flat p-3 text-center text-xs text-slate-400">You joined with a friend's code.</p>
          ) : (
            <ReferralApply />
          )}
        </div>
      )}
    </>
  )
}