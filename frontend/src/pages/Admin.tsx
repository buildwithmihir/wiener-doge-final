import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useSession } from '../auth/AuthContext'
import { PageTitle } from '../components/ui'
import MarketsAdmin from './admin/MarketsAdmin'
import SystemAdmin from './admin/SystemAdmin'
import UsersAdmin from './admin/UsersAdmin'
import WithdrawalsAdmin from './admin/WithdrawalsAdmin'

type Tab = 'markets' | 'withdrawals' | 'users' | 'system'

function chipClass(active: boolean): string {
  return `shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition ${
    active ? 'bg-neon-blue/20 text-neon-blue ring-1 ring-neon-blue/60' : 'bg-white/5 text-slate-300 hover:text-white'
  }`
}

export default function AdminPage() {
  const { user } = useSession()
  const [tab, setTab] = useState<Tab>('markets')
  const isAdmin = user.roles.includes('admin')
  const isMod = isAdmin || user.roles.includes('moderator')
  // The UI only hides things. The server re-checks the role from the database on every admin call.
  if (!isMod) return <Navigate to="/" replace />

  const tabs: { key: Tab; label: string }[] = [
    { key: 'markets', label: 'Markets' },
    ...(isAdmin
      ? ([
          { key: 'withdrawals', label: 'Withdrawals' },
          { key: 'users', label: 'Users' },
          { key: 'system', label: 'System' },
        ] as { key: Tab; label: string }[])
      : []),
  ]
  return (
    <>
      <PageTitle title="Admin" subtitle="Every action needs a reason and is audited." />
      <div className="mb-3 flex gap-2 overflow-x-auto" role="tablist">
        {tabs.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={chipClass(tab === t.key)} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'markets' && <MarketsAdmin isAdmin={isAdmin} />}
      {tab === 'withdrawals' && isAdmin && <WithdrawalsAdmin />}
      {tab === 'users' && isAdmin && <UsersAdmin />}
      {tab === 'system' && isAdmin && <SystemAdmin />}
    </>
  )
}