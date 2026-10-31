import { useQuery } from '@tanstack/react-query'
import { Lock, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import type { WagerStatus } from '../lib/types'
import { Progress } from './shadcn/progress'

/** Progress of the wager rule: deposits and bonuses must be wagered N x (default 2x) before withdrawing. */
export function WagerCard() {
  const wager = useQuery({ queryKey: ['wager'], queryFn: () => api<WagerStatus>('/wallet/wager'), staleTime: 10_000 })
  if (!wager.data) return null
  const w = wager.data
  const required = BigInt(w.required.units)
  const wagered = BigInt(w.wagered.units)
  const pct = required <= 0n ? 100 : Math.min(100, Number((wagered * 100n) / required))

  return (
    <div className="glass-flat space-y-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-white">
          {w.met ? <ShieldCheck className="h-4 w-4 text-up" aria-hidden /> : <Lock className="h-4 w-4 text-gold" aria-hidden />}
          Withdrawal wager ({w.multiplier}x)
        </p>
        <span className={`text-xs font-bold ${w.met ? 'text-up' : 'text-gold'}`}>{w.met ? 'Unlocked' : `${pct}%`}</span>
      </div>
      <Progress value={pct} aria-label="Wager progress" className="h-2 bg-black/40" />
      <p className="text-xs text-slate-400">
        {w.met ? (
          'You can withdraw.'
        ) : (
          <>
            Wager <span className="num font-semibold text-white">{usd(w.remaining)}</span> more on settled bets to withdraw.
          </>
        )}
      </p>
      <p className="text-[11px] text-slate-500">
        Deposits and bonuses must be wagered {w.multiplier}x. Only settled bets count: open and cashed-out bets do not.
      </p>
    </div>
  )
}