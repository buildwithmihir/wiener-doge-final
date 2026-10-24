import { Target } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { distancePct } from '../lib/ladder'
import { price } from '../lib/format'
import type { Market } from '../lib/types'
import { cn } from '../lib/utils'

/** Strip of target prices. The chosen one turns blue and scrolls into view. */
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
  const selectedRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [selectedId])

  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
        <Target className="h-3.5 w-3.5 text-primary" /> Pick a target price
      </p>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 pt-1 [scrollbar-width:none]" role="radiogroup" aria-label="Target price">
        {strikes.map((m) => {
          const on = m.id === selectedId
          const dist = distancePct(m.target_price, lastPrice)
          const near = dist === '+0.0%' || dist === '-0.0%'
          return (
            <button
              key={m.id}
              ref={on ? selectedRef : undefined}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onSelect(m.id)}
              className={cn(
                'relative min-w-[6rem] shrink-0 rounded-2xl border px-3 py-2.5 text-left transition-all duration-300 active:scale-95',
                on ? 'pick-selected scale-[1.03]' : 'pick-idle',
              )}
            >
              <span className="font-display-num block text-sm font-bold">{price(m.target_price)}</span>
              <span className={cn('block text-[11px] font-medium', on ? 'text-white/85' : near ? 'text-gold' : 'text-muted-foreground')}>
                {near ? 'At the price' : dist ?? '—'}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
