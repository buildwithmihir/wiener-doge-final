import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

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

export function EmptyState({ title, text, action }: { title: string; text: string; action?: ReactNode }) {
  return (
    <div className="glass p-6 text-center">
      <p className="text-base font-semibold text-white">{title}</p>
      <p className="mx-auto mt-1 max-w-xs text-sm text-slate-400">{text}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'up' | 'down' | 'demo' }) {
  const tones = {
    neutral: 'border-white/15 bg-white/5 text-slate-200',
    up: 'border-up/40 bg-up-soft text-up',
    down: 'border-down/40 bg-down-soft text-down',
    demo: 'border-gold/40 bg-gold/10 text-gold',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}>
      {tone === 'demo' && <span className="h-1.5 w-1.5 rounded-full bg-gold" aria-hidden />}
      {children}
    </span>
  )
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-bold text-white">{title}</h1>
      {subtitle && <p className="text-sm text-slate-400">{subtitle}</p>}
    </div>
  )
}
