import { Target } from 'lucide-react'
import { distancePct } from '../lib/ladder'
import { price } from '../lib/format'
import type { Market } from '../lib/types'

/** Horizontal strip of target prices. The chosen strike is blue and stays highlighted. */
export function StrikeLadder({
  strikes,
  selectedId,
  lastPrice,
  onSelect,
}: {
  strikes: Market[]
  selectedId: string
  lastPrice: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
        <Target className="h-3.5 w-3.5 text-neon-blue" /> Target price
      </p>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 [scrollbar-width:none]" role="radiogroup" aria-label="Target price">
        {strikes.map((m) => {
          const on = m.id === selectedId
          const dist = distancePct(m.target_price, lastPrice)
          return (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onSelect(m.id)}
              className={`min-w-[5.5rem] shrink-0 rounded-xl border px-3 py-2 text-left transition duration-200 active:scale-95 ${
                on ? 'pick-selected' : 'pick-idle'
              }`}
            >
              <span className="num block text-sm font-bold">{price(m.target_price)}</span>
              <span className={`num block text-[11px] ${on ? 'text-white/80' : 'text-slate-400'}`}>{dist ?? '—'}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
