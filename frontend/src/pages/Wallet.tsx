import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { usd } from '../lib/format'
import type { Wallet as WalletData } from '../lib/types'
import { Badge, ErrorState, PageTitle, Spinner } from '../components/ui'

export default function WalletPage() {
  const wallet = useQuery({ queryKey: ['wallet'], queryFn: () => api<WalletData>('/wallet') })

  return (
    <>
      <PageTitle title="Wallet" subtitle="Demo credits only. No cash value, not redeemable." />
      {wallet.isPending && <Spinner />}
      {wallet.isError && <ErrorState message="Could not load your wallet." onRetry={() => void wallet.refetch()} />}
      {wallet.data && (
        <div className="space-y-3">
          <div className="glass p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-400">Available</p>
              <Badge tone="demo">DEMO</Badge>
            </div>
            <p className="num mt-1 text-4xl font-bold text-white">{usd(wallet.data.available)}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="glass-flat p-4">
              <p className="text-xs text-slate-400">In open predictions</p>
              <p className="num mt-1 text-xl font-semibold">{usd(wallet.data.reserved)}</p>
            </div>
            <div className="glass-flat p-4">
              <p className="text-xs text-slate-400">Total</p>
              <p className="num mt-1 text-xl font-semibold">{usd(wallet.data.total)}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <button type="button" className="btn-ghost" disabled>
              Deposit
            </button>
            <button type="button" className="btn-ghost" disabled>
              Withdraw
            </button>
          </div>
          <p className="text-center text-xs text-slate-500">Deposits and withdrawals are disabled in demo mode.</p>
        </div>
      )}
    </>
  )
}
