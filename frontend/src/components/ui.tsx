import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { Badge as ShadBadge } from './shadcn/badge'

export type IconTone = 'blue' | 'gold' | 'green' | 'violet' | 'pink' | 'orange'

const TONES: Record<IconTone, string> = {
  blue: 'border-sky-400/30 from-sky-500/30 to-blue-600/20 text-sky-300 shadow-[0_0_20px_rgba(56,189,248,0.25)]',
  gold: 'border-amber-400/30 from-amber-400/30 to-orange-500/20 text-amber-300 shadow-[0_0_20px_rgba(251,191,36,0.25)]',
  green: 'border-emerald-400/30 from-emerald-400/30 to-teal-500/20 text-emerald-300 shadow-[0_0_20px_rgba(52,211,153,0.25)]',
  violet: 'border-violet-400/30 from-violet-500/30 to-fuchsia-500/20 text-violet-300 shadow-[0_0_20px_rgba(167,139,250,0.25)]',
  pink: 'border-pink-400/30 from-pink-500/30 to-rose-500/20 text-pink-300 shadow-[0_0_20px_rgba(244,114,182,0.25)]',
  orange: 'border-orange-400/30 from-orange-500/30 to-red-500/20 text-orange-300 shadow-[0_0_20px_rgba(251,146,60,0.25)]',
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex items-center justify-center py-10 text-neon-blue">
      <Loader2 className="h-6 w-6 animate-spin" />
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="glass-flat p-5 text-center">
      <p className="text-sm text-slate-300">{message}</p>
      {onRetry && (
        <button type="button" className="btn-ghost mt-4" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, text, action, icon, tone = 'blue' }: { title: string; text: string; action?: ReactNode; icon?: LucideIcon; tone?: IconTone }) {
  return (
    <div className="glass animate-fade-up p-6 text-center">
      {icon && <IconTile icon={icon} tone={tone} className="mx-auto mb-3 h-12 w-12" />}
      <p className="text-base font-semibold text-white">{title}</p>
      <p className="mx-auto mt-1 max-w-xs text-sm text-slate-400">{text}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'up' | 'down' | 'demo' }) {
  return (
    <ShadBadge variant={tone === 'demo' ? 'gold' : tone}>
      {tone === 'demo' && <span className="h-1.5 w-1.5 rounded-full bg-gold" aria-hidden />}
      {children}
    </ShadBadge>
  )
}

export function IconTile({ icon: Icon, className = '', tone = 'blue' }: { icon: LucideIcon; className?: string; tone?: IconTone }) {
  return (
    <span
      aria-hidden
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border bg-gradient-to-br ${TONES[tone]} ${className}`}
    >
      <Icon className="h-5 w-5" />
    </span>
  )
}

export function PageTitle({ title, subtitle, icon, tone = 'blue' }: { title: string; subtitle?: string; icon?: LucideIcon; tone?: IconTone }) {
  return (
    <div className="mb-5 mt-3 flex animate-fade-up items-center gap-3.5">
      {icon && <IconTile icon={icon} tone={tone} className="h-11 w-11" />}
      <div>
        <h1 className="font-display text-xl font-bold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="text-sm text-slate-400">{subtitle}</p>}
      </div>
    </div>
  )
}