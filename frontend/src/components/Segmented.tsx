import type { ReactNode } from 'react'
import { Tabs, TabsList, TabsTrigger } from './shadcn/tabs'

export interface SegOption<T extends string | number> {
  value: T
  label: ReactNode
  sub?: ReactNode
}

/** Timeframe / round tabs (shadcn Tabs). */
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
  return (
    <Tabs
      value={String(value)}
      onValueChange={(v) => {
        const found = options.find((o) => String(o.value) === v)
        if (found) onChange(found.value)
      }}
    >
      <TabsList aria-label={label}>
        {options.map((o) => (
          <TabsTrigger key={String(o.value)} value={String(o.value)}>
            <span className="text-sm font-semibold">{o.label}</span>
            {o.sub && <span className="text-[11px] opacity-80">{o.sub}</span>}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
