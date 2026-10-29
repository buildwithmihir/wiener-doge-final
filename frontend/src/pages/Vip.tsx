import { useQuery } from '@tanstack/react-query'
import { Award, Check, Crown, Gem, Gift, Lock, Medal, Rocket, Sparkles, TrendingUp, type LucideIcon } from 'lucide-react'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import { progressPct, tierPct } from '../lib/vip'
import type { VipResponse, VipTier } from '../lib/types'
import { Progress } from '../components/shadcn/progress'
import { ErrorState, PageTitle, Spinner } from '../components/ui'

interface TierStyle {
  grad: string // emblem gradient
  glow: string // hero glow colour
  text: string
  ring: string
  Icon: LucideIcon
}

const TIER: Record<string, TierStyle> = {
  Bronze: {
    grad: 'from-[#8a4b1f] via-[#c46d2f] to-[#f0a15f]',
    glow: 'rgba(232,146,77,0.35)',
    text: 'text-bronze',
    ring: 'ring-[#e8924d]/40',
    Icon: Medal,
  },
  Silver: {
    grad: 'from-[#5b6477] via-[#a9b2c6] to-[#eef1f8]',
    glow: 'rgba(199,204,217,0.30)',
    text: 'text-silver',
    ring: 'ring-[#c7ccd9]/40',
    Icon: Award,
  },
  Gold: {
    grad: 'from-[#b8791a] via-[#f5b942] to-[#ffe08a]',
    glow: 'rgba(245,185,66,0.38)',
    text: 'text-gold',
    ring: 'ring-[#f5b942]/40',
    Icon: Crown,
  },
  Platinum: {
    grad: 'from-[#0e7490] via-[#22d3ee] to-[#e0f2fe]',
    glow: 'rgba(34,211,238,0.38)',
    text: 'text-platinum',
    ring: 'ring-[#67e8f9]/40',
    Icon: Gem,
  },
}

const FALLBACK: TierStyle = TIER.Bronze!
const styleOf = (name: string): TierStyle => TIER[name] ?? FALLBACK

function Emblem({ name, unlocked, size = 'lg' }: { name: string; unlocked: boolean; size?: 'lg' | 'xl' }) {
  const s = styleOf(name)
  const Icon = s.Icon
  const box = size === 'xl' ? 'h-20 w-20 rounded-3xl' : 'h-16 w-16 rounded-2xl'
  const icon = size === 'xl' ? 'h-10 w-10' : 'h-8 w-8'
  return (
    <span
      className={`relative flex shrink-0 items-center justify-center bg-gradient-to-br ${s.grad} text-white ring-1 ring-white/25 ${box} ${
        unlocked ? '' : 'opacity-40 grayscale'
      }`}
    >
      <Icon className={`${icon} drop-shadow`} strokeWidth={2.2} />
      {unlocked && <Check className="absolute -bottom-1.5 -right-1.5 h-5 w-5 rounded-full bg-up p-0.5 text-black ring-2 ring-black" />}
    </span>
  )
}

function Hero({ vip }: { vip: VipResponse }) {
  const cur = vip.current
  const s = cur ? styleOf(cur.name) : null
  return (
    <section
      className="relative mb-5 overflow-hidden rounded-3xl border border-white/10 bg-card p-5 shadow-card"
      style={{ backgroundImage: `radial-gradient(420px 220px at 85% -10%, ${s?.glow ?? 'rgba(59,130,246,0.25)'}, transparent 70%)` }}
    >
      <div className="flex items-center gap-4">
        {cur ? (
          <Emblem name={cur.name} unlocked size="xl" />
        ) : (
          <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-3xl bg-white/5 text-slate-300 ring-1 ring-white/15">
            <Rocket className="h-10 w-10" strokeWidth={2} />
          </span>
        )}
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">Your tier</p>
          <p className={`font-display text-3xl font-extrabold tracking-tight ${s?.text ?? 'text-white'}`}>{cur?.name ?? 'Starter'}</p>
          <p className="mt-0.5 text-xs text-slate-400">{cur ? 'Keep staking to climb higher.' : 'Stake to unlock your first tier.'}</p>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-black/30 p-3 ring-1 ring-white/5">
          <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <TrendingUp className="h-3.5 w-3.5 text-sky-400" /> Total staked
          </p>
          <p className="num mt-1 text-xl font-bold text-white">{usd(vip.total_staked)}</p>
        </div>
        <div className="rounded-2xl bg-black/30 p-3 ring-1 ring-white/5">
          <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <Gift className="h-3.5 w-3.5 text-amber-400" /> Next bonus
          </p>
          <p className="num mt-1 text-xl font-bold text-white">{vip.next ? usd(vip.next.reward) : '—'}</p>
        </div>
      </div>

      {vip.next && vip.remaining_to_next ? (
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-xs">
            <span className="font-medium text-slate-300">Progress to {vip.next.name}</span>
            <span className="num font-semibold text-white">{progressPct(vip)}%</span>
          </div>
          <Progress value={progressPct(vip)} aria-label={`Progress to ${vip.next.name}`} className="h-2.5 bg-black/40" />
          <p className="mt-2 text-xs text-slate-400">
            <span className="num font-semibold text-white">{usd(vip.remaining_to_next)}</span> more to reach {vip.next.name}
          </p>
        </div>
      ) : (
        <p className="mt-4 flex items-center gap-2 rounded-xl bg-amber-400/10 px-3 py-2 text-sm font-semibold text-amber-300 ring-1 ring-amber-400/30">
          <Crown className="h-4 w-4" /> Top tier reached
        </p>
      )}
    </section>
  )
}

function TierCard({ t, total, isNext }: { t: VipTier; total: string; isNext: boolean }) {
  const s = styleOf(t.name)
  const pct = t.unlocked ? 100 : tierPct(total, t)
  return (
    <li className={`glass-flat animate-fade-up p-4 ${isNext ? `ring-1 ${s.ring}` : ''}`}>
      <div className="flex items-center gap-4">
        <Emblem name={t.name} unlocked={t.unlocked} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className={`font-display text-lg font-bold ${t.unlocked ? s.text : 'text-slate-200'}`}>{t.name}</p>
            {t.unlocked ? (
              <span className="rounded-full bg-up/15 px-2.5 py-0.5 text-[11px] font-bold text-up">Unlocked</span>
            ) : isNext ? (
              <span className="rounded-full bg-primary/15 px-2.5 py-0.5 text-[11px] font-bold text-primary">Next</span>
            ) : (
              <span className="flex items-center gap-1 rounded-full bg-white/5 px-2.5 py-0.5 text-[11px] font-semibold text-slate-400">
                <Lock className="h-3 w-3" /> Locked
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-400">
            Stake <span className="num font-semibold text-slate-200">{usd(t.min_staked)}</span> to unlock
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-xl bg-black/25 px-3 py-2">
          <p className="text-[11px] text-slate-500">Bonus</p>
          <p className="num font-bold text-gold">{usd(t.reward)}</p>
        </div>
        <div className="rounded-xl bg-black/25 px-3 py-2">
          <p className="text-[11px] text-slate-500">Bonus status</p>
          <p className={`font-semibold ${t.reward_paid ? 'text-up' : 'text-slate-300'}`}>{t.reward_paid ? 'Received' : t.unlocked ? 'Processing' : 'On unlock'}</p>
        </div>
      </div>

      {!t.unlocked && (
        <div className="mt-3">
          <Progress value={pct} aria-label={`${t.name} progress`} className="h-1.5 bg-black/40" />
          <p className="num mt-1 text-right text-[11px] text-slate-500">{pct}%</p>
        </div>
      )}

      {t.benefits.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {t.benefits.map((b) => (
            <li key={b} className="flex items-center gap-1 rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-slate-300">
              <Sparkles className="h-3 w-3 text-neon-cyan" />
              {b}
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

export default function VipPage() {
  const vip = useQuery({ queryKey: ['vip'], queryFn: () => api<VipResponse>('/vip') })

  return (
    <>
      <PageTitle icon={Crown} tone="gold" title="VIP Club" subtitle="Stake more, unlock tiers, earn bonuses." />
      {vip.isPending && <Spinner />}
      {vip.isError && <ErrorState message="Could not load VIP tiers." onRetry={() => void vip.refetch()} />}
      {vip.data && (
        <>
          <Hero vip={vip.data} />
          <p className="mb-3 px-1 text-sm font-semibold text-white">All tiers</p>
          <ul className="space-y-3">
            {vip.data.tiers.map((t) => (
              <TierCard key={t.id} t={t} total={vip.data.total_staked.units} isNext={vip.data.next?.id === t.id} />
            ))}
          </ul>
        </>
      )}
    </>
  )
}