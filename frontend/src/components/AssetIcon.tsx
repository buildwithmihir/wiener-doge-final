const STYLES: Record<string, string> = {
  SOL: 'from-[#14f195] to-[#9945ff]',
  WIENER: 'from-[#ffb347] to-[#ff5e62]',
}

export function AssetIcon({ symbol, size = 48 }: { symbol: string; size?: number }) {
  const style = STYLES[symbol] ?? 'from-neon-blue to-neon-violet'
  return (
    <span
      aria-hidden
      style={{ width: size, height: size, fontSize: size * 0.34 }}
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${style} font-extrabold text-ink-950 ring-2 ring-white/10`}
    >
      {symbol.slice(0, 3)}
    </span>
  )
}
