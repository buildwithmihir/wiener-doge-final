import { BarChart3, History, Star, Trophy, User, Wallet } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Badge } from './ui'

const TABS = [
  { to: '/', label: 'Markets', icon: BarChart3, end: true },
  { to: '/wallet', label: 'Wallet', icon: Wallet, end: false },
  { to: '/history', label: 'History', icon: History, end: false },
  { to: '/vip', label: 'VIP', icon: Star, end: false },
  { to: '/profile', label: 'Profile', icon: User, end: false },
] as const

export function Layout() {
  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col">
      <header className="sticky top-0 z-20 flex items-center justify-between gap-2 border-b border-white/5 bg-background/70 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur">
        <Link to="/" className="flex items-center gap-2" aria-label="WienerDoge home">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-neon-blue to-neon-violet shadow-glow">
            <BarChart3 className="h-5 w-5 text-white" />
          </span>
          <span className="font-display bg-gradient-to-r from-neon-cyan via-neon-blue to-neon-violet bg-clip-text text-lg font-extrabold text-transparent">
            WienerDoge
          </span>
        </Link>
        <div className="flex items-center gap-3">
          <Badge tone="demo">DEMO</Badge>
          <Link to="/leaderboard" aria-label="Leaderboard" className="text-slate-300 hover:text-white">
            <Trophy className="h-5 w-5" />
          </Link>
        </div>
      </header>

      <main className="flex-1 px-4 pb-32 pt-4">
        <Outlet />
      </main>

      <nav
        aria-label="Main"
        className="fixed inset-x-3 bottom-3 z-20 mx-auto flex max-w-md justify-around rounded-3xl border border-white/10 bg-card/90 px-2 pb-2 pt-2 shadow-card backdrop-blur-xl"
      >
        {TABS.map(({ to, label, icon: Icon, end }) => (
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
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
