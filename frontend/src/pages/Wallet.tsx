import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Copy, Wallet as WalletIcon } from 'lucide-react'
import { useRef, useState } from 'react'
import { Badge, ErrorState, PageTitle, Spinner } from '../components/ui'
import { Button } from '../components/shadcn/button'
import { Input } from '../components/shadcn/input'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '../components/shadcn/sheet'
import { api, ApiError, newIdempotencyKey } from '../lib/api'
import { dateTime, usd } from '../lib/format'
import { parseDemoToUnits, unitsToDemo } from '../lib/money'
import type { DepositInfo, PayAsset, PublicConfig, WagerStatus, Wallet as WalletData, WithdrawalItem, WithdrawalStatus } from '../lib/types'
import { WagerCard } from '../components/WagerCard'

const ASSETS: PayAsset[] = ['SOL', 'WIENER']

const STATUS_LABEL: Record<WithdrawalStatus, string> = {
  pending: 'Awaiting approval',
  approved: 'Approved',
  sending: 'Sending',
  sent: 'Sent',
  rejected: 'Rejected',
  failed: 'Failed (retrying)',
}

function AssetToggle({ value, onChange }: { value: PayAsset; onChange: (a: PayAsset) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Asset">
      {ASSETS.map((a) => (
        <button
          key={a}
          type="button"
          role="radio"
          aria-checked={value === a}
          onClick={() => onChange(a)}
          className={`rounded-xl border px-3 py-2.5 text-sm font-bold transition ${value === a ? 'pick-selected' : 'pick-idle'}`}
        >
          {a}
        </button>
      ))}
    </div>
  )
}

function DepositSheet({ onClose }: { onClose: () => void }) {
  const info = useQuery({ queryKey: ['deposit-address'], queryFn: () => api<DepositInfo>('/deposit/address') })
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied('yes')
    } catch {
      setCopied('no')
    }
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetTitle className="font-display text-lg font-bold text-white">Deposit</SheetTitle>
        <SheetDescription className="mb-4 text-xs text-muted-foreground">
          Send SOL or WIENER on the Solana network to your personal address. Your balance is credited in $ after the transfer is finalized.
        </SheetDescription>

        {info.isPending && <Spinner />}
        {info.isError && (
          <p role="alert" className="text-sm text-down">
            {info.error instanceof ApiError ? info.error.message : 'Could not load your deposit address.'}
          </p>
        )}
        {info.data && (
          <div className="space-y-3">
            <div className="rounded-xl border border-dashed border-neon-blue/40 bg-ink-900 p-3">
              <p className="mb-1 text-xs text-slate-400">Your {info.data.network} address (SOL and WIENER)</p>
              <p className="break-all font-mono text-sm text-white">{info.data.address}</p>
            </div>
            <Button type="button" className="w-full" variant="secondary" onClick={() => void copy(info.data.address)}>
              <Copy className="h-4 w-4" aria-hidden />
              {copied === 'yes' ? 'Copied' : copied === 'no' ? 'Copy failed: select the address manually' : 'Copy address'}
            </Button>
            <ul className="space-y-1 text-xs text-slate-400">
              <li>Minimum deposit: {usd(info.data.min_deposit)}</li>
              <li>Only send SOL or WIENER. Other tokens are not credited.</li>
              <li>Send only on the Solana network. Other networks are lost.</li>
              <li>Value is converted to $ using the market price at the time it is credited.</li>
            </ul>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

function WithdrawSheet({ available, onClose }: { available: bigint; onClose: () => void }) {
  const qc = useQueryClient()
  const [asset, setAsset] = useState<PayAsset>('SOL')
  const [amount, setAmount] = useState('')
  const [address, setAddress] = useState('')
  const keyRef = useRef(newIdempotencyKey())

  const send = useMutation({
    mutationFn: () =>
      api<WithdrawalItem>('/withdrawals', {
        method: 'POST',
        headers: { 'Idempotency-Key': keyRef.current },
        body: { asset, amount: amount.trim(), address: address.trim() },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['wallet'] })
      void qc.invalidateQueries({ queryKey: ['withdrawals'] })
    },
  })

  // a retry of the same request reuses the key; an edited request is a new action
  const edit = (apply: () => void) => {
    apply()
    keyRef.current = newIdempotencyKey()
    send.reset()
  }

  const units = parseDemoToUnits(amount)
  let problem: string | null = null
  if (units === null || units === 0n) problem = 'Enter an amount in $, for example 25.'
  else if (units > available) problem = 'Not enough balance.'
  else if (address.trim().length < 32 || address.trim().length > 44) problem = 'Enter a valid Solana wallet address.'

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetTitle className="font-display text-lg font-bold text-white">Withdraw</SheetTitle>
        <SheetDescription className="mb-4 text-xs text-muted-foreground">
          Choose how you want to receive your balance. Withdrawals are reviewed by our team before they are sent.
        </SheetDescription>

        {send.data ? (
          <div className="py-4 text-center">
            <p className="text-lg font-semibold text-white">Request received</p>
            <p className="mt-1 text-sm text-slate-400">
              {usd(send.data.amount)} in {send.data.asset} is awaiting approval. You can follow it in your withdrawal list.
            </p>
            <Button type="button" className="mt-5 w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <AssetToggle value={asset} onChange={(a) => edit(() => setAsset(a))} />
            <div>
              <label htmlFor="wd-amount" className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Amount ($)
              </label>
              <div className="mt-1 flex gap-2">
                <Input id="wd-amount" inputMode="decimal" autoComplete="off" value={amount} onChange={(e) => edit(() => setAmount(e.target.value))} placeholder="25" />
                <Button type="button" variant="outline" onClick={() => edit(() => setAmount(unitsToDemo(available)))}>
                  Max
                </Button>
              </div>
              <p className="mt-1 text-xs text-slate-500">Available: {usd(unitsToDemo(available))}</p>
            </div>
            <div>
              <label htmlFor="wd-address" className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Your Solana wallet address
              </label>
              <Input id="wd-address" autoComplete="off" autoCapitalize="off" spellCheck={false} value={address} onChange={(e) => edit(() => setAddress(e.target.value))} placeholder="Paste address" className="mt-1 font-mono text-sm" />
            </div>
            <p className="text-xs text-slate-500">
              You receive {asset} worth the amount above, calculated with the market price when it is sent. Double-check the address: transfers cannot be reversed.
            </p>
            {(send.error || (problem && (amount || address))) && (
              <p role="alert" className="text-sm text-down">
                {send.error instanceof ApiError ? send.error.message : send.error ? 'Something went wrong. Try again.' : problem}
              </p>
            )}
            <Button type="button" size="lg" className="w-full" disabled={problem !== null || send.isPending} onClick={() => send.mutate()}>
              {send.isPending ? 'Sending…' : `Request ${asset} withdrawal`}
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

function WithdrawalRow({ w }: { w: WithdrawalItem }) {
  const tone = w.status === 'sent' ? 'up' : w.status === 'rejected' || w.status === 'failed' ? 'down' : 'neutral'
  return (
    <li className="glass-flat p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold text-white">
          {usd(w.amount)} <span className="text-slate-400">as {w.asset}</span>
        </p>
        <Badge tone={tone}>{STATUS_LABEL[w.status]}</Badge>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        {dateTime(w.created_at)}
        {w.native_amount ? ` · ${w.native_amount} ${w.asset}` : ''}
      </p>
      {w.note && w.status === 'rejected' && <p className="mt-1 text-xs text-slate-300">Reason: {w.note}</p>}
      {w.tx_signature && (
        <a className="mt-1 block text-xs text-neon-blue underline" href={`https://solscan.io/tx/${w.tx_signature}`} target="_blank" rel="noreferrer">
          View transaction
        </a>
      )}
    </li>
  )
}

export default function WalletPage() {
  const wallet = useQuery({ queryKey: ['wallet'], queryFn: () => api<WalletData>('/wallet') })
  const config = useQuery({ queryKey: ['config'], queryFn: () => api<PublicConfig>('/config'), staleTime: 60_000 })
  const withdrawals = useQuery({
    queryKey: ['withdrawals'],
    queryFn: () => api<{ items: WithdrawalItem[] }>('/withdrawals'),
    enabled: config.data?.payments_enabled === true,
    refetchInterval: 30_000,
  })
  const wager = useQuery({ queryKey: ['wager'], queryFn: () => api<WagerStatus>('/wallet/wager') })
  const [sheet, setSheet] = useState<'deposit' | 'withdraw' | null>(null)

  const live = config.data?.payments_enabled === true
  const wagerMet = wager.data?.met !== false
    const items = withdrawals.data?.items ?? []
  const inFlight = items
    .filter((w) => w.status === 'pending' || w.status === 'approved' || w.status === 'sending')
    .reduce((sum, w) => sum + BigInt(w.amount.units), 0n)

  return (
    <>
      <PageTitle
        icon={WalletIcon}
        title="Wallet"
        subtitle="Your balance in $. Deposit or withdraw SOL or WIENER."
      />
      {wallet.isPending && <Spinner />}
      {wallet.isError && <ErrorState message="Could not load your wallet." onRetry={() => void wallet.refetch()} />}
      {wallet.data && (
        <div className="space-y-3">
          <div className="glass p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-400">Available</p>
              
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
          <WagerCard />\n          {inFlight > 0n && (
            <div className="glass-flat flex items-center justify-between p-3 text-sm">
              <span className="text-slate-400">Pending withdrawals</span>
              <span className="num font-semibold text-white">{usd(unitsToDemo(inFlight))}</span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <button type="button" className="btn-primary" disabled={!live} onClick={() => setSheet('deposit')}>
              <ArrowDown className="h-4 w-4" aria-hidden /> Deposit
            </button>
            <button type="button" className="btn-ghost" disabled={!live || !wagerMet} onClick={() => setSheet('withdraw')}>
              <ArrowUp className="h-4 w-4" aria-hidden /> Withdraw
            </button>
          </div>
          {!live && <p className="text-center text-xs text-slate-500">Deposits and withdrawals are temporarily unavailable.</p>}

          {live && items.length > 0 && (
            <>
              <p className="px-1 pt-2 text-sm font-semibold text-white">Withdrawals</p>
              <ul className="space-y-2">
                {items.map((w) => (
                  <WithdrawalRow key={w.id} w={w} />
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {sheet === 'deposit' && <DepositSheet onClose={() => setSheet(null)} />}
      {sheet === 'withdraw' && wallet.data && <WithdrawSheet available={BigInt(wallet.data.available.units)} onClose={() => setSheet(null)} />}
    </>
  )
}