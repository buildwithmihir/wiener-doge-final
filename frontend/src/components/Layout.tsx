import { useQuery } from '@tanstack/react-query'
import { BarChart3, BookOpen, History, LifeBuoy, Star, Trophy, User, Wallet as WalletIcon } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import { HELP_URL, SUPPORT_URL } from '../lib/links'
import type { Wallet } from '../lib/types'
import { NotificationsBell } from './NotificationsBell'

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
      <header className="sticky top-0 z-20 border-b border-white/5 bg-background/70 px-4 pb-2.5 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur">
        {/* Row 1: full app name, leaderboard, notifications */}
        <div className="flex items-center justify-between gap-2">
          <Link to="/" className="flex min-w-0 flex-1 items-center gap-2.5" aria-label="WienerDoge Prediction Market home">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-blue-600 shadow-glow">
              <BarChart3 className="h-5 w-5 text-white" />
            </span>
            <span className="flex flex-col leading-tight">
              <span className="font-display text-[17px] font-extrabold tracking-tight text-white">WienerDoge</span>
              <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.14em] text-sky-300/90">
                Prediction Market
              </span>
            </span>
          </Link>
          <div className="flex shrink-0 items-center gap-2">
            <Link
              to="/leaderboard"
              aria-label="Leaderboard"
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30 transition active:scale-95"
            >
              <Trophy className="h-[18px] w-[18px]" />
            </Link>
            <NotificationsBell />
          </div>
        </div>

        {/* Row 2: balance, help guide, support */}
        <div className="mt-2.5 flex items-center gap-2">
          <Link
            to="/wallet"
            aria-label="Open wallet"
            className="flex min-w-0 flex-1 items-center justify-between rounded-2xl border border-white/10 bg-white/5 py-1.5 pl-3.5 pr-1.5 transition active:scale-[0.99]"
          >
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gold">Balance</span>
            <span className="flex items-center gap-2.5">
              <span className="num text-base font-bold text-white">{wallet.data ? usd(wallet.data.available) : '—'}</span>
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-teal-600">
                <WalletIcon className="h-4 w-4 text-white" />
              </span>
            </span>
          </Link>
          <a
            href={HELP_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Help guide"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/30 transition active:scale-95"
          >
            <BookOpen className="h-[18px] w-[18px]" />
          </a>
          <a
            href={SUPPORT_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Support"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/30 transition active:scale-95"
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