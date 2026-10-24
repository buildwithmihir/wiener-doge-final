import { useQuery } from '@tanstack/react-query'
import { Check, Crown, Gem, Lock, Star, Medal, ShieldCheck, type LucideIcon } from 'lucide-react'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import { progressPct } from '../lib/vip'
import type { VipResponse, VipTier } from '../lib/types'
import { Badge, ErrorState, PageTitle, Spinner } from '../components/ui'

const TIER_COLOR: Record<string, string> = {
  Bronze: 'text-bronze',
  Silver: 'text-silver',
  Gold: 'text-gold',
  Platinum: 'text-platinum',
}

const TIER_ICON: Record<string, LucideIcon> = { Bronze: Medal, Silver: ShieldCheck, Gold: Crown, Platinum: Gem }

function TierCard({ t, isNext }: { t: VipTier; isNext: boolean }) {
  return (
    <li className={`glass-flat animate-fade-up p-4 ${isNext ? 'ring-1 ring-neon-blue/50' : ''} ${t.unlocked ? '' : 'opacity-90'}`}>
      <div className="flex items-center justify-between">
        <p className={`flex items-center gap-3 text-lg font-bold ${TIER_COLOR[t.name] ?? 'text-white'}`}>
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-ink-900/70 shadow-glow">
            {(() => {
              const Icon = TIER_ICON[t.name] ?? Medal
              return <Icon className="h-5 w-5" />
            })()}
          </span>
          {t.name}
        </p>
        {t.unlocked ? (
          <Badge tone="up">
            <Check className="mr-1 inline h-3 w-3" aria-hidden />
            Unlocked
          </Badge>
        ) : (
          <Badge>
            <Lock className="mr-1 inline h-3 w-3" aria-hidden />
            {usd(t.min_staked)} staked
          </Badge>
        )}
      </div>
      <p className="mt-1 text-sm text-slate-300">
        One-time bonus: <span className="num font-semibold text-white">{usd(t.reward)}</span> demo credits
      </p>
      {t.benefits.length > 0 && (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-slate-400">
          {t.benefits.map((b) => (
            <li key={b}>{b}</li>
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
      <PageTitle icon={Star} title="VIP" subtitle="Stake demo credits to unlock tiers. Rewards are demo credits too." />
      {vip.isPending && <Spinner />}
      {vip.isError && <ErrorState message="Could not load VIP tiers." onRetry={() => void vip.refetch()} />}
      {vip.data && (
        <div className="space-y-3">
          <div className="glass p-5">
            <p className="text-sm text-slate-400">Total staked</p>
            <p className="num mt-1 text-3xl font-bold text-white">{usd(vip.data.total_staked)}</p>
            <p className="mt-1 text-sm text-slate-300">
              Current tier: <span className="font-semibold">{vip.data.current?.name ?? 'None yet'}</span>
            </p>
            {vip.data.next && vip.data.remaining_to_next ? (
              <>
                <div
                  className="mt-3 h-2 overflow-hidden rounded-full bg-white/10"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={progressPct(vip.data)}
                  aria-label={`Progress to ${vip.data.next.name}`}
                >
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-neon-blue to-neon-violet"
                    style={{ width: `${progressPct(vip.data)}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  {usd(vip.data.remaining_to_next)} more to reach {vip.data.next.name}
                </p>
              </>
            ) : (
              <p className="mt-2 text-xs text-up">You reached the top tier.</p>
            )}
          </div>
          <ul className="space-y-3">
            {vip.data.tiers.map((t) => (
              <TierCard key={t.id} t={t} isNext={vip.data.next?.id === t.id} />
            ))}
          </ul>
          <p className="px-1 text-center text-xs text-slate-500">Demo credits only. No cash value, not redeemable.</p>
        </div>
      )}
    </>
  )
}
