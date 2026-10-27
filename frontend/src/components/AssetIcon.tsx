import { Dog } from 'lucide-react'
import { useId, type ReactElement } from 'react'

/** Official Solana logo (three bars) with its green-to-purple gradient, drawn on a black circle. */
function SolGlyph({ s }: { s: number }) {
  const id = useId()
  return (
    <svg width={s} height={s * 0.784} viewBox="0 0 397.7 311.7" aria-hidden="true">
      <defs>
        <linearGradient id={id} gradientUnits="userSpaceOnUse" x1="0" y1="311.7" x2="397.7" y2="0">
          <stop offset="0" stopColor="#00FFA3" />
          <stop offset="1" stopColor="#DC1FFF" />
        </linearGradient>
      </defs>
      <g fill={`url(#${id})`}>
        <path d="M64.6 237.9c2.4-2.4 5.7-3.8 9.2-3.8h317.4c5.8 0 8.7 7 4.6 11.1l-62.7 62.7c-2.4 2.4-5.7 3.8-9.2 3.8H6.5c-5.8 0-8.7-7-4.6-11.1l62.7-62.7z" />
        <path d="M64.6 3.8C67.1 1.4 70.4 0 73.8 0h317.4c5.8 0 8.7 7 4.6 11.1l-62.7 62.7c-2.4 2.4-5.7 3.8-9.2 3.8H6.5c-5.8 0-8.7-7-4.6-11.1L64.6 3.8z" />
        <path d="M333.1 120.1c-2.4-2.4-5.7-3.8-9.2-3.8H6.5c-5.8 0-8.7 7-4.6 11.1l62.7 62.7c2.4 2.4 5.7 3.8 9.2 3.8h317.4c5.8 0 8.7-7 4.6-11.1l-62.7-62.7z" />
      </g>
    </svg>
  )
}

const STYLES: Record<string, { ring: string; glow: string; glyph: (s: number) => ReactElement }> = {
  SOL: {
    ring: 'ring-white/15',
    glow: 'shadow-[0_0_22px_rgba(153,69,255,0.35)]',
    glyph: (s) => <SolGlyph s={s} />,
  },
  WIENER: {
    ring: 'ring-[#ffb347]/50',
    glow: 'shadow-[0_0_22px_rgba(255,150,60,0.35)]',
    glyph: (s) => <Dog style={{ width: s, height: s }} strokeWidth={2.2} className="text-[#ffb347]" />,
  },
}

export function AssetIcon({ symbol, size = 48 }: { symbol: string; size?: number }) {
  const style = STYLES[symbol] ?? {
    ring: 'ring-white/15',
    glow: 'shadow-glow',
    glyph: (s: number) => <Dog style={{ width: s, height: s }} className="text-white" />,
  }

  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#1c1c1c] to-black ring-2 ${style.ring} ${style.glow}`}
    >
      {style.glyph(size * 0.5)}
    </span>
  )
}