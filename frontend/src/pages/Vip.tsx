import { useQuery } from '@tanstack/react-query'
import {
  Award,
  Check,
  Crown,
  Gem,
  Gift,
  Lock,
  Medal,
  Sparkles,
  Star,
  type LucideIcon,
} from 'lucide-react'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import { progressPct } from '../lib/vip'
import type { VipResponse, VipTier } from '../lib/types'
import { Progress } from '../components/shadcn/progress'
import { ErrorState, PageTitle, Spinner } from '../components/ui'

const TIER: Record<string, { grad: string; glow: string; text: string; Icon: LucideIcon }> = {
  Bronze: {
    grad: 'from-[#8a4b1f] via-[#c46d2f] to-[#f0a15f]',
    glow: 'shadow-[0_0_28px_rgba(232,146,77,0.45)]',
    text: 'text-bronze',
    Icon: Medal,
  },
  Silver: {
    grad: 'from-[#5b6477] via-[#a9b2c6] to-[#eef1f8]',
    glow: 'shadow-[0_0_28px_rgba(199,204,217,0.4)]',
    text: 'text-silver',
    Icon: Award,
  },
  Gold: {
    grad: 'from-[#b8791a] via-[#f5b942] to-[#ffe08a]',
    glow: 'shadow-[0_0_32px_rgba(245,185,66,0.55)]',
    text: 'text-gold',
    Icon: Crown,
  },
  Platinum: {
    grad: 'from-[#0e7490] via-[#22d3ee] to-[#e0f2fe]',
    glow: 'shadow-[0_0_34px_rgba(34,211,238,0.55)]',
    text: 'text-platinum',
    Icon: Gem,
  },
}

const FALLBACK = TIER.Bronze!

function TierRow({ t, isNext, last }: { t: VipTier; isNext: boolean; last: boolean }) {
  const s = TIER[t.name] ?? FALLBACK
  const Icon = s.Icon

  return (
    <li className="relative flex animate-fade-up gap-4">
      {!last && (
        <span
          aria-hidden
          className={`absolute left-[27px] top-14 h-[calc(100%-2rem)] w-0.5 ${
            t.unlocked ? 'bg-gradient-to-b from-up to-white/10' : 'bg-white/10'
          }`}
        />
      )}

      <span
        className={`relative z-10 flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${s.grad} text-white ring-1 ring-white/20 ${
          t.unlocked ? s.glow : 'opacity-40 grayscale'
        }`}
      >
        <Icon className="h-7 w-7 drop-shadow" strokeWidth={2.2} />
        {t.unlocked && <Check className="absolute -bottom-1 -right-1 h-5 w-5 rounded-full bg-up p-0.5 text-black" />}
      </span>

      <div className={`glass-flat mb-4 min-w-0 flex-1 p-4 ${isNext ? 'ring-1 ring-primary/60' : ''}`}>
        <div className="flex items-center justify-between">
          <p className={`font-display text-lg font-bold ${t.unlocked ? s.text : 'text-slate-300'}`}>{t.name}</p>

          {t.unlocked ? (
            <span className="rounded-full bg-up/15 px-2.5 py-0.5 text-xs font-bold text-up">Unlocked</span>
          ) : (
            <span className="flex items-center gap-1 rounded-full bg-white/5 px-2.5 py-0.5 text-xs font-semibold text-slate-400">
              <Lock className="h-3 w-3" /> {usd(t.min_staked)}
            </span>
          )}
        </div>

        <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-300">
          <Gift className="h-4 w-4 text-gold" />
          Bonus <span className="num font-bold text-white">{usd(t.reward)}</span> demo credits
        </p>

        {t.benefits.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {t.benefits.map((b) => (
              <li key={b} className="flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-slate-300">
                <Sparkles className="h-3 w-3 text-neon-cyan" />
                {b}
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  )
}

export default function VipPage() {
  const vip = useQuery({ queryKey: ['vip'], queryFn: () => api<VipResponse>('/vip') })

  const cur = vip.data?.current ? TIER[vip.data.current.name] ?? FALLBACK : null
  const HeroIcon = cur?.Icon ?? Star

  return (
    <>
      <PageTitle icon={Star} title="VIP Club" subtitle="Stake demo credits to level up. Rewards are demo credits too." />

      {vip.isPending && <Spinner />}

      {vip.isError && <ErrorState message="Could not load VIP tiers." onRetry={() => void vip.refetch()} />}

      {vip.data && (
        <div>
          <div
            className={`relative mb-6 overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br ${
              cur?.grad ?? 'from-neutral-900 via-neutral-800 to-black'
            } p-5 shadow-card`}
          >
            <div aria-hidden className="absolute -right-8 -top-8 h-40 w-40 rounded-full bg-white/15 blur-2xl" />

            <div className="relative flex items-center gap-4">
              <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-black/40 text-white ring-1 ring-white/20 backdrop-blur">
                <HeroIcon className="h-9 w-9" strokeWidth={2.2} />
              </span>

              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-white/80">Current tier</p>
                <p className="font-display text-3xl font-extrabold text-white">{vip.data.current?.name ?? 'Rookie'}</p>
              </div>
            </div>

            {/* all tiers at a glance */}
            <div className="relative mt-4 flex gap-2">
              {vip.data.tiers.map((t) => {
                const s = TIER[t.name] ?? FALLBACK
                const I = s.Icon
                return (
                  <span
                    key={t.id}
                    title={t.name}
                    className={`flex h-10 w-10 items-center justify-center rounded-xl bg-black/40 ring-1 ring-white/10 ${
                      t.unlocked ? s.text : 'text-white/30'
                    }`}
                  >
                    <I className="h-5 w-5" strokeWidth={2.2} />
                  </span>
                )
              })}
            </div>

            <p className="relative mt-4 text-sm text-white/80">Total staked</p>
            <p className="num relative text-3xl font-bold text-white">{usd(vip.data.total_staked)}</p>

            {vip.data.next && vip.data.remaining_to_next ? (
              <div className="relative mt-3">
                <Progress value={progressPct(vip.data)} aria-label={`Progress to ${vip.data.next.name}`} className="h-3 bg-black/40" />
                <p className="mt-2 text-xs font-medium text-white/90">
                  {usd(vip.data.remaining_to_next)} more to reach <b>{vip.data.next.name}</b>
                </p>
              </div>
            ) : (
              <p className="relative mt-3 text-sm font-bold text-white">👑 Top tier reached!</p>
            )}
          </div>

          <ul>
            {vip.data.tiers.map((t, i) => (
              <TierRow key={t.id} t={t} isNext={vip.data.next?.id === t.id} last={i === vip.data.tiers.length - 1} />
            ))}
          </ul>

          <p className="px-1 text-center text-xs text-slate-500">Demo credits only. No cash value, not redeemable.</p>
        </div>
      )}
    </>
  )
}