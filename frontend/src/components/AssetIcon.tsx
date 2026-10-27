
import { Dog } from 'lucide-react'
import type { ReactElement } from 'react'

const Sol = ({ s }: { s: number }) => (
  <svg
    width={s}
    height={s}
    viewBox="0 0 24 24"
    fill="#fff"
    aria-hidden="true"
  >
    <path d="M6.2 15.6h13.2c.3 0 .5.4.3.6l-2.4 2.5a.8.8 0 0 1-.6.3H3.5c-.3 0-.5-.4-.3-.6l2.4-2.5c.1-.2.4-.3.6-.3Z" />
    <path d="M6.2 5.4h13.2c.3 0 .5.4.3.6L17.3 8.5a.8.8 0 0 1-.6.3H3.5c-.3 0-.5-.4-.3-.6l2.4-2.5c.1-.2.4-.3.6-.3Z" />
    <path
      d="M17.3 10.4H4.1a.8.8 0 0 0-.6.3L1.1 13.2c-.2.2 0 .6.3.6h13.2c.2 0 .4-.1.6-.3l2.4-2.5c.2-.2 0-.6-.3-.6Z"
      transform="translate(2.9 -0.2)"
    />
  </svg>
)



const STYLES: Record<string, { bg: string; glyph: (s: number) => ReactElement }> = {
  SOL: {
    bg: 'from-[#14f195] to-[#9945ff]',
    glyph: (s) => <Sol s={s} />,
  },
  WIENER: {
    bg: 'from-[#ffb347] to-[#ff5e62]',
    glyph: (s) => (
      <Dog style={{ width: s, height: s }} strokeWidth={2.4} className="text-white" />
    ),
  },
}

export function AssetIcon({
  symbol,
  size = 48,
}: {
  symbol: string
  size?: number
}) {
  const style = STYLES[symbol] ?? {
    bg: 'from-neon-blue to-neon-violet',
    glyph: (s: number) => (
      <Dog
        style={{ width: s, height: s }}
        className="text-white"
      />
    ),
  }

  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${style.bg} shadow-glow ring-2 ring-white/25`}
    >
      {style.glyph(size * 0.55)}
    </span>
  )
}
