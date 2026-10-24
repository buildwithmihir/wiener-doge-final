import type { ReactNode } from 'react'

export interface SegOption<T extends string | number> {
  value: T
  label: ReactNode
  sub?: ReactNode
}

/** Pill tabs with a sliding highlight. */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
}: {
  options: SegOption<T>[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  const idx = Math.max(0, options.findIndex((o) => o.value === value))
  return (
    <div role="tablist" aria-label={label} className="relative flex rounded-2xl border border-white/10 bg-ink-900/70 p-1">
      <span
        aria-hidden
        className="absolute inset-y-1 rounded-xl bg-gradient-to-r from-neon-blue to-neon-violet shadow-glow transition-transform duration-300 ease-out"
        style={{ width: `calc((100% - 0.5rem) / ${options.length})`, transform: `translateX(${idx * 100}%)` }}
      />
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="tab"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={`relative z-10 flex-1 rounded-xl px-2 py-2 text-center transition-colors ${
            o.value === value ? 'text-white' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <span className="block text-sm font-semibold">{o.label}</span>
          {o.sub && <span className="block text-[11px] opacity-80">{o.sub}</span>}
        </button>
      ))}
    </div>
  )
}
