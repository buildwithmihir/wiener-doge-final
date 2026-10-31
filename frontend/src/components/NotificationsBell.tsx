import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Bell, Gift, Star, Trophy, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'
import { dateTime } from '../lib/format'
import type { NotificationsResponse } from '../lib/types'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from './shadcn/sheet'

const ICON: Record<string, { Icon: LucideIcon; cls: string }> = {
  market_result: { Icon: Trophy, cls: 'bg-emerald-400/15 text-emerald-300' },
  deposit: { Icon: ArrowDown, cls: 'bg-sky-400/15 text-sky-300' },
  withdrawal: { Icon: ArrowUp, cls: 'bg-violet-400/15 text-violet-300' },
  raffle: { Icon: Gift, cls: 'bg-pink-400/15 text-pink-300' },
  referral_reward: { Icon: Gift, cls: 'bg-amber-400/15 text-amber-300' },
  vip_unlock: { Icon: Star, cls: 'bg-amber-400/15 text-amber-300' },
}
const FALLBACK = { Icon: Bell, cls: 'bg-white/10 text-slate-300' }

/** Bell in the header corner. Shows won bets, deposits, withdrawals, raffles and other announcements. */
export function NotificationsBell() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const list = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api<NotificationsResponse>('/notifications'),
    refetchInterval: 30_000,
  })
  const markRead = useMutation({
    mutationFn: () => api('/notifications/read', { method: 'POST' }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
  const unread = list.data?.unread ?? 0

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (!next && unread > 0) markRead.mutate() // mark as read when closing, so new ones stay highlighted while open
  }

  return (
    <>
      <button
        type="button"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
        onClick={() => onOpenChange(true)}
        className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-sky-400/10 text-sky-300 ring-1 ring-sky-400/30 transition active:scale-95"
      >
        <Bell className="h-[18px] w-[18px]" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-down px-1 text-[10px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <Sheet open onOpenChange={onOpenChange}>
          <SheetContent aria-describedby={undefined} className="max-h-[80vh] overflow-y-auto">
            <SheetTitle className="font-display text-lg font-bold text-white">Notifications</SheetTitle>
            <SheetDescription className="mb-3 text-xs text-muted-foreground">Wins, deposits, withdrawals, raffles and updates.</SheetDescription>
            {list.isPending && <p className="py-6 text-center text-sm text-slate-400">Loading…</p>}
            {list.data && list.data.items.length === 0 && <p className="py-8 text-center text-sm text-slate-400">Nothing yet.</p>}
            <ul className="space-y-2">
              {list.data?.items.map((n) => {
                const { Icon, cls } = ICON[n.type] ?? FALLBACK
                return (
                  <li key={n.id} className={`flex gap-3 rounded-2xl p-3 ${n.read ? 'bg-white/[0.03]' : 'bg-primary/10 ring-1 ring-primary/30'}`}>
                    <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${cls}`}>
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-white">{n.title}</p>
                      <p className="text-xs text-slate-300">{n.body}</p>
                      <p className="mt-1 text-[11px] text-slate-500">{dateTime(n.created_at)}</p>
                    </div>
                  </li>
                )
              })}
            </ul>
          </SheetContent>
        </Sheet>
      )}
    </>
  )
}