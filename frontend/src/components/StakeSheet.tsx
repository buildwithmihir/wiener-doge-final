import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, CheckCircle2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, newIdempotencyKey } from '../lib/api'
import { durationFull, price, usd } from '../lib/format'
import { parseDemoToUnits, payoutUnits, unitsToDemo } from '../lib/money'
import { haptic } from '../lib/telegram'
import { Button } from './shadcn/button'
import { Input } from './shadcn/input'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from './shadcn/sheet'
import type { Market, Prediction, Wallet } from '../lib/types'

const QUICK = ['5', '10', '25', '50']

export function StakeSheet({
  market,
  direction,
  onClose,
  onPlaced,
}: {
  market: Market
  direction: 'above' | 'below'
  onClose: () => void
  onPlaced?: () => void
}) {
  const client = useQueryClient()
  const [stake, setStake] = useState('10')
  const inputRef = useRef<HTMLInputElement>(null)
  // One key per user action. It changes whenever the stake changes, so a retry after a network
  // error is safe (same key = the server returns the same prediction) but an edited stake is new.
  const keyRef = useRef(newIdempotencyKey())

  const wallet = useQuery({ queryKey: ['wallet'], queryFn: () => api<Wallet>('/wallet') })
  const place = useMutation({
    mutationFn: () =>
      api<Prediction>('/predictions', {
        method: 'POST',
        headers: { 'Idempotency-Key': keyRef.current },
        body: { market_id: market.id, direction, stake, expected_target_price: market.target_price },
      }),
    onSuccess: () => {
      haptic('success')
      onPlaced?.()
      void client.invalidateQueries({ queryKey: ['wallet'] })
      void client.invalidateQueries({ queryKey: ['predictions'] })
      void client.invalidateQueries({ queryKey: ['markets'] })
    },
    onError: () => haptic('error'),
  })

  useEffect(() => {
    inputRef.current?.focus()
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const units = parseDemoToUnits(stake)
  const min = BigInt(market.min_stake.units)
  const max = BigInt(market.max_stake.units)
  const available = wallet.data ? BigInt(wallet.data.available.units) : null

  let problem: string | null = null
  if (units === null || units === 0n) problem = 'Enter an amount, for example 10.'
  else if (units < min) problem = `Minimum stake is ${usd(market.min_stake)}.`
  else if (units > max) problem = `Maximum stake is ${usd(market.max_stake)}.`
  else if (available !== null && units > available) problem = 'Not enough balance.'

  const win = units !== null && problem === null ? payoutUnits(units, market.payout_multiplier) : null
  const isAbove = direction === 'above'
  const placed = place.data
  const maxAllowed = available !== null ? (available < max ? available : max) : max

  const changeStake = (value: string) => {
    setStake(value)
    keyRef.current = newIdempotencyKey()
    place.reset()
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <SheetTitle className={`flex items-center gap-2 font-display text-lg font-bold ${isAbove ? 'text-up' : 'text-down'}`}>
              {isAbove ? <ArrowUp className="h-5 w-5" /> : <ArrowDown className="h-5 w-5" />}
              {isAbove ? 'Above' : 'Below'} {price(market.target_price)}
            </SheetTitle>
            <SheetDescription className="text-xs text-muted-foreground">
              {market.symbol} · wins if the price at close is {isAbove ? '≥' : '<'} {price(market.target_price)}
            </SheetDescription>
          </div>
        </div>

        {placed ? (
          <div className="py-4 text-center">
            <CheckCircle2 className="mx-auto h-12 w-12 animate-pop text-up" />
            <p className="mt-2 text-lg font-semibold">Prediction placed</p>
            <p className="mt-1 text-sm text-slate-400">
              {usd(placed.stake)} on {placed.direction.toUpperCase()} · potential win {usd(placed.potential_payout)}
            </p>
            <Button type="button" className="mt-5 w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <>
            <label htmlFor="stake" className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Stake ($)
            </label>
            <Input
              id="stake"
              ref={inputRef}
              inputMode="decimal"
              autoComplete="off"
              value={stake}
              onChange={(event) => changeStake(event.target.value)}
              className="font-display-num mt-1 h-14 text-2xl font-bold"
            />

            <div className="mt-3 flex gap-2">
              {QUICK.map((amount) => (
                <Button key={amount} type="button" className="flex-1" variant="secondary" size="sm" onClick={() => changeStake(amount)}>
                  {amount}
                </Button>
              ))}
              <Button type="button" className="flex-1" variant="outline" size="sm" disabled={available === null} onClick={() => changeStake(unitsToDemo(maxAllowed))}>
                Max
              </Button>
            </div>

            <div className="mt-4 rounded-xl border border-primary/30 bg-primary/10 p-3 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">Asset</span><span className="font-semibold">{market.symbol}</span></div>
              <div className="mt-1 flex justify-between"><span className="text-slate-400">Timeframe</span><span className="font-semibold">{durationFull(market.duration_seconds)}</span></div>
              <div className="mt-1 flex justify-between"><span className="text-slate-400">Target</span><span className="num font-semibold">{price(market.target_price)}</span></div>
              <div className="mt-1 flex justify-between"><span className="text-slate-400">Your call</span><span className={`font-semibold ${isAbove ? 'text-up' : 'text-down'}`}>{isAbove ? 'ABOVE' : 'BELOW'}</span></div>
              <div className="mt-1 flex justify-between"><span className="text-slate-400">Odds</span><span className="num font-semibold text-gold">{market.payout_multiplier}x</span></div>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-slate-400">Available</span>
              <span className="num">{wallet.data ? usd(wallet.data.available) : '…'}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-sm">
              <span className="text-slate-400">Potential win ({market.payout_multiplier}x)</span>
              <span className="num font-semibold text-up">{win !== null ? usd(unitsToDemo(win)) : '—'}</span>
            </div>

            {(problem || place.error) && (
              <p role="alert" className="mt-3 text-sm text-down">
                {place.error instanceof ApiError ? place.error.message : place.error ? 'Something went wrong. Try again.' : problem}
              </p>
            )}

            <Button type="button" size="lg" className="mt-4 w-full" disabled={problem !== null || place.isPending} onClick={() => place.mutate()}>
              {place.isPending ? 'Placing…' : `Place ${isAbove ? 'Above' : 'Below'} prediction`}
            </Button>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
