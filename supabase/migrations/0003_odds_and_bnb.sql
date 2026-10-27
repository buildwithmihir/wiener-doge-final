begin;

alter table markets
  add column if not exists payout_above_bps integer
    check (payout_above_bps is null or (payout_above_bps > 10000 and payout_above_bps <= 100000)),
  add column if not exists payout_below_bps integer
    check (payout_below_bps is null or (payout_below_bps > 10000 and payout_below_bps <= 100000));
-- (no backfill: old markets fall back to payout_bps via coalesce)

create or replace function wd_markets_odds_guard() returns trigger
language plpgsql as $$
begin
  if old.status <> 'draft' and (
       new.payout_above_bps is distinct from old.payout_above_bps
    or new.payout_below_bps is distinct from old.payout_below_bps) then
    raise exception 'market_terms_immutable_after_draft';
  end if;
  return new;
end $$;
drop trigger if exists trg_markets_odds_guard on markets;
create trigger trg_markets_odds_guard before update on markets
  for each row execute function wd_markets_odds_guard();

-- prediction guard: odds now depend on direction
create or replace function wd_predictions_guard() returns trigger
language plpgsql as $$
declare
  m markets%rowtype;
  bps integer;
begin
  if tg_op = 'DELETE' then raise exception 'predictions_are_permanent'; end if;

  if tg_op = 'INSERT' then
    select * into m from markets where id = new.market_id;
    if not found then raise exception 'market_not_found'; end if;
    if m.status <> 'open' then raise exception 'market_not_open'; end if;
    if now() < m.opens_at then raise exception 'market_not_started'; end if;
    if now() >= m.betting_closes_at then raise exception 'betting_closed'; end if;
    if new.stake < m.min_stake or new.stake > m.max_stake then raise exception 'stake_out_of_range'; end if;
    bps := case when new.direction = 'above' then coalesce(m.payout_above_bps, m.payout_bps)
                else coalesce(m.payout_below_bps, m.payout_bps) end;
    if new.target_price_snapshot <> m.target_price
       or new.payout_bps_snapshot <> bps
       or new.closes_at_snapshot <> m.closes_at then
      raise exception 'terms_mismatch';
    end if;
    return new;
  end if;

  if new.user_id <> old.user_id or new.market_id <> old.market_id or new.direction <> old.direction
     or new.stake <> old.stake or new.payout_bps_snapshot <> old.payout_bps_snapshot
     or new.target_price_snapshot <> old.target_price_snapshot
     or new.closes_at_snapshot <> old.closes_at_snapshot
     or new.potential_payout <> old.potential_payout
     or new.idempotency_key <> old.idempotency_key
     or new.created_at <> old.created_at then
    raise exception 'prediction_terms_immutable';
  end if;
  if old.status <> 'open' and new.status <> old.status then
    raise exception 'prediction_already_final';
  end if;
  return new;
end $$;

-- place_prediction: pick the odds of the chosen direction
create or replace function place_prediction(
  p_user uuid, p_market uuid, p_direction text, p_stake bigint, p_key text
) returns predictions
language plpgsql as $$
declare
  u users%rowtype; m markets%rowtype; ex predictions%rowtype; pred predictions%rowtype;
  av uuid; rs uuid; bps integer;
  tx uuid := gen_random_uuid(); pid uuid := gen_random_uuid();
begin
  select * into ex from predictions where user_id = p_user and idempotency_key = p_key;
  if found then return ex; end if;

  select * into u from users where id = p_user;
  if not found then raise exception 'user_not_found'; end if;
  if u.status <> 'active' then raise exception 'user_not_active'; end if;

  select * into m from markets where id = p_market for share;
  if not found then raise exception 'market_not_found'; end if;

  bps := case when p_direction = 'above' then coalesce(m.payout_above_bps, m.payout_bps)
              else coalesce(m.payout_below_bps, m.payout_bps) end;

  select id into av from ledger_accounts where owner_user_id = p_user and account_type = 'user_available';
  select id into rs from ledger_accounts where owner_user_id = p_user and account_type = 'user_reserved';

  begin
    insert into predictions(id, user_id, market_id, direction, stake, payout_bps_snapshot,
                            target_price_snapshot, closes_at_snapshot, potential_payout, idempotency_key)
    values (pid, p_user, p_market, p_direction, p_stake, bps, m.target_price, m.closes_at,
            greatest(p_stake, (p_stake * bps) / 10000), p_key)
    returning * into pred;
  exception when unique_violation then
    select * into ex from predictions where user_id = p_user and idempotency_key = p_key;
    if found then return ex; end if;
    raise;
  end;

  begin
    insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
      (tx, av, -p_stake, 'stake_reserve', 'prediction', pid, 'stake:' || pid, 'Stake reserved for prediction'),
      (tx, rs,  p_stake, 'stake_reserve', 'prediction', pid, 'stake:' || pid, 'Stake reserved for prediction');
  exception when check_violation then
    raise exception 'insufficient_balance';
  end;

  perform wd_audit(p_user, 'user', 'prediction.place', 'prediction', pid::text, null, to_jsonb(pred), null);
  return pred;
end $$;

-- BNB asset (CoinGecko id: binancecoin)
insert into assets(symbol, name, decimals, is_prediction_asset, provider_key, provider_ref)
values ('BNB', 'BNB', 8, true, 'coingecko', 'binancecoin')
on conflict (symbol) do update set provider_key = 'coingecko', provider_ref = 'binancecoin', is_prediction_asset = true;

commit;