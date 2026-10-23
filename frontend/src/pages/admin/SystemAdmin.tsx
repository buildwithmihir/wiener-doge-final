import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { dateTime } from '../../lib/format'
import type { AuditItem } from '../../lib/types'
import { Badge, ErrorState, Spinner } from '../../components/ui'

interface Reconcile {
  ok: boolean
  issues: { check: string; detail: string }[]
}

export default function SystemAdmin() {
  const rec = useQuery({ queryKey: ['admin-reconcile'], queryFn: () => api<Reconcile>('/admin/reconcile') })
  const audit = useInfiniteQuery({
    queryKey: ['admin-audit'],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) =>
      api<{ items: AuditItem[]; next_cursor: number | null }>(`/admin/audit?limit=30${pageParam ? `&before=${pageParam}` : ''}`),
    getNextPageParam: (last) => last.next_cursor,
  })
  const items = audit.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <div className="space-y-3">
      <div className="glass-flat space-y-2 p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-white">Ledger integrity</p>
          {rec.data && <Badge tone={rec.data.ok ? 'up' : 'down'}>{rec.data.ok ? 'All checks pass' : `${rec.data.issues.length} issue(s)`}</Badge>}
        </div>
        {rec.isPending && <Spinner />}
        {rec.isError && <ErrorState message="Could not run the check." onRetry={() => void rec.refetch()} />}
        {rec.data?.issues.map((i) => (
          <p key={`${i.check}-${i.detail}`} className="text-xs text-down">
            {i.check}: {i.detail}
          </p>
        ))}
        <button type="button" className="btn-ghost w-full" onClick={() => void rec.refetch()} disabled={rec.isFetching}>
          Run check again
        </button>
      </div>
      <p className="px-1 text-sm font-semibold text-white">Audit log</p>
      {audit.isPending && <Spinner />}
      {audit.isError && <ErrorState message="Could not load the audit log." onRetry={() => void audit.refetch()} />}
      <ul className="space-y-2">
        {items.map((a) => (
          <li key={a.id} className="glass-flat p-3 text-xs">
            <p className="font-semibold text-white">
              {a.action} <span className="font-normal text-slate-400">· {a.actor_type}</span>
            </p>
            <p className="text-slate-400">
              {dateTime(a.created_at)}
              {a.entity_type ? ` · ${a.entity_type}` : ''}
            </p>
            {a.reason && <p className="mt-1 text-slate-300">{a.reason}</p>}
          </li>
        ))}
      </ul>
      {audit.hasNextPage && (
        <button type="button" className="btn-ghost w-full" onClick={() => void audit.fetchNextPage()} disabled={audit.isFetchingNextPage}>
          {audit.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      )}
    </div>
  )
}
