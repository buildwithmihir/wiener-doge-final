import { useQuery } from '@tanstack/react-query'
import { BarChart3, History, LifeBuoy, Star, Trophy, User, Wallet as WalletIcon } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import type { Wallet } from '../lib/types'

// Set VITE_SUPPORT_URL in Vercel (e.g. https://t.me/your_support_username)
const SUPPORT_URL = (import.meta.env.VITE_SUPPORT_URL as string | undefined) || 'https://t.me/YOUR_SUPPORT_USERNAME'

const TABS = [
  { to: '/', label: 'Markets', icon: BarChart3, end: true, color: 'text-sky-400' },
  { to: '/wallet', label: 'Wallet', icon: WalletIcon, end: false, color: 'text-emerald-400' },
  { to: '/history', label: 'History', icon: History, end: false, color: 'text-violet-400' },
  { to: '/vip', label: 'VIP', icon: Star, end: false, color: 'text-amber-400' },
  { to: '/profile', label: 'Profile', icon: User, end: false, color: 'text-pink-400' },
] as const

export function Layout() {
  const wallet = useQuery({ queryKey: ['wallet'], queryFn: () => api<Wallet>('/wallet') })
  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col">
      <header className="sticky top-0 z-20 flex items-center justify-between gap-2 border-b border-white/5 bg-background/70 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur">
        <Link to="/" className="flex min-w-0 items-center gap-2.5" aria-label="WienerDoge Prediction Market home">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-blue-600 shadow-glow">
            <BarChart3 className="h-5 w-5 text-white" />
          </span>
          <span className="flex min-w-0 flex-col leading-tight">
            <span className="font-display truncate text-[17px] font-extrabold tracking-tight text-white">WienerDoge</span>
            <span className="truncate text-[10px] font-semibold uppercase tracking-[0.18em] text-sky-300/90">Prediction Market</span>
          </span>
        </Link>
        <div className="flex shrink-0 items-center gap-2.5">
          <Link
            to="/wallet"
            aria-label="Open wallet"
            className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 py-1 pl-3 pr-1 transition active:scale-95"
          >
            <span className="text-right leading-tight">
              <span className="num block text-sm font-bold text-white">{wallet.data ? usd(wallet.data.available) : '—'}</span>
              <span className="block text-[9px] font-semibold uppercase tracking-wider text-gold">Balance</span>
            </span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-teal-600">
              <WalletIcon className="h-4 w-4 text-white" />
            </span>
          </Link>
          <Link to="/leaderboard" aria-label="Leaderboard" className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30 transition active:scale-95">
            <Trophy className="h-[18px] w-[18px]" />
          </Link>
          <a
            href={SUPPORT_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Support"
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/30 transition active:scale-95"
          >
            <LifeBuoy className="h-[18px] w-[18px]" />
          </a>
        </div>
      </header>

      <main className="flex-1 px-4 pb-32 pt-4">
        <Outlet />
      </main>

      <nav
        aria-label="Main"
        className="fixed inset-x-3 bottom-3 z-20 mx-auto flex max-w-md justify-around rounded-3xl border border-white/10 bg-card/90 px-2 pb-2 pt-2 shadow-card backdrop-blur-xl"
      >
        {TABS.map(({ to, label, icon: Icon, end, color }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex min-w-14 flex-col items-center gap-1 rounded-xl px-3 py-1.5 text-[11px] font-medium transition ${
                isActive ? 'bg-gradient-to-br from-primary to-accent text-white shadow-glow' : 'text-muted-foreground hover:text-white'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={`h-5 w-5 ${isActive ? 'text-white' : color}`} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}