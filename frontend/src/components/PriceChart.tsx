import { useId } from 'react'
import { buildPlot, type PlotBox } from '../lib/chart'
import { dateTime, price } from '../lib/format'
import type { ChartResponse } from '../lib/types'

const BOX: PlotBox = { width: 340, height: 190, left: 8, right: 62, top: 16, bottom: 24 }

function clock(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(iso))
}

export function PriceChart({
  points,
  lastPrice,
  target,
}: {
  points: ChartResponse['points']
  lastPrice: string | null
  target?: string | null
}) {
  const gradientId = useId()
  const plot = buildPlot(points, BOX, 5, target ? Number(target) : null)

  if (!plot) {
    return (
      <div className="flex h-[190px] items-center justify-center rounded-xl border border-white/10 text-sm text-slate-400">
        Collecting price data…
      </div>
    )
  }

  const first = points[0]!
  const mid = points[Math.floor(points.length / 2)]!
  const last = points[points.length - 1]!

  return (
    <svg
      viewBox={`0 0 ${BOX.width} ${BOX.height}`}
      className="w-full"
      role="img"
      aria-label={`Price chart from ${dateTime(first.t)} to ${dateTime(last.t)}`}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
        </linearGradient>
      </defs>
      {plot.ticks.map((tick) => (
        <g key={tick.y}>
          <line x1={BOX.left} x2={BOX.width - BOX.right} y1={tick.y} y2={tick.y} stroke="rgba(255,255,255,0.07)" />
          <text x={BOX.width - BOX.right + 6} y={tick.y + 4} fontSize="10" fill="#9aa5c8">
            {tick.value.toFixed(plot.decimals)}
          </text>
        </g>
      ))}
      <path d={plot.area} fill={`url(#${gradientId})`} />
      <path d={plot.line} fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={plot.last.x} cy={plot.last.y} r="4" fill="#fff" stroke="#8b5cf6" strokeWidth="2" />
      {plot.targetY !== null && target && (
        <g className="animate-fade-in">
          <line x1={BOX.left} x2={BOX.width - BOX.right} y1={plot.targetY} y2={plot.targetY} stroke="#4f8cff" strokeWidth="1.5" strokeDasharray="5 4" />
          <rect x={BOX.left + 2} y={plot.targetY - 9} width={104} height={18} rx={5} fill="#1d4ed8" />
          <text x={BOX.left + 54} y={plot.targetY + 4} fontSize="10" fontWeight="700" fill="#fff" textAnchor="middle">
            {plot.targetOff === 'above' ? '▲ ' : plot.targetOff === 'below' ? '▼ ' : ''}TARGET {price(target)}
          </text>
        </g>
      )}
      {lastPrice && (
        <g>
          <rect x={BOX.width - BOX.right + 2} y={plot.last.y - 9} width={58} height={18} rx={5} fill="#4f46e5" />
          <text x={BOX.width - BOX.right + 31} y={plot.last.y + 4} fontSize="10" fontWeight="700" fill="#fff" textAnchor="middle">
            {Number(lastPrice).toFixed(plot.decimals)}
          </text>
        </g>
      )}
      <g fontSize="10" fill="#9aa5c8">
        <text x={BOX.left} y={BOX.height - 6}>{clock(first.t)}</text>
        <text x={(BOX.width - BOX.right + BOX.left) / 2} y={BOX.height - 6} textAnchor="middle">{clock(mid.t)}</text>
        <text x={BOX.width - BOX.right} y={BOX.height - 6} textAnchor="end">{clock(last.t)}</text>
      </g>
    </svg>
  )
}
