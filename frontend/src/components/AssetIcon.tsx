import { Coins, Dog } from 'lucide-react'

const STYLES: Record<string, { bg: string; Icon: typeof Coins }> = {
  SOL: { bg: 'from-[#14f195] to-[#9945ff]', Icon: Coins },
  WIENER: { bg: 'from-[#ffb347] to-[#ff5e62]', Icon: Dog },
}

export function AssetIcon({ symbol, size = 48 }: { symbol: string; size?: number }) {
  const { bg, Icon } = STYLES[symbol] ?? { bg: 'from-neon-blue to-neon-violet', Icon: Coins }
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${bg} text-ink-950 shadow-glow ring-2 ring-white/20`}
    >
      <Icon style={{ width: size * 0.5, height: size * 0.5 }} strokeWidth={2.4} />
    </span>
  )
}
