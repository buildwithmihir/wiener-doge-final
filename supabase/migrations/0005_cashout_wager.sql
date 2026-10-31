-- =====================================================================
-- 0005_cashout_wager.sql
--  * cashout for live predictions (new status 'cashed_out', ledger kind 'cashout')
--  * wager counts ONLY settled bets (won / lost). Open and cashed-out bets never count.
--  * 2x wager rule on deposits + bonuses before a withdrawal can be requested
--  * notification preferences for payments + raffles
--  * settings for automatic markets
-- Run in the Supabase SQL Editor AFTER 0004_payments.sql (safe to re-run).
-- =====================================================================
begin;

-- ---------------------------------------------------------------------
-- 1. statuses / kinds
-- ---------------------------------------------------------------------
alter table predictions drop constraint if exists predictions_status_check;
alter table predictions add constraint predictions_status_check
  check (status in ('open','won','lost','refunded','cashed_out'));

alter table ledger_entries drop constraint if exists ledger_entries_kind_check;
alter table ledger_entries add constraint ledger_entries_kind_check check (kind in (
  'signup_grant','stake_reserve','win_payout','loss_settle','refund','admin_adjustment',
  'referral_reward','vip_reward','deposit','withdraw_hold','withdraw_release','withdraw_sent','cashout'));

-- ---------------------------------------------------------------------
-- 2. notification preferences + settings
-- ---------------------------------------------------------------------
alter table notification_preferences
  add column if not exists payments boolean not null default true,
  add column if not exists raffles  boolean not null default true;

insert into application_settings(key, value, description) values
  ('markets.auto_enabled',     'true',                    'Worker creates new market rounds automatically'),
  ('markets.auto_durations',   '[86400,172800,604800]',   'Timeframes (seconds) the worker keeps open automatically'),
  ('payments.wager_multiplier','2',                       'Wager needed (x) on deposits + bonuses before withdrawing'),
  ('cashout.cutoff_seconds',   '300',                     'No cashout in the last N seconds before a market closes')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------
-- 3. wager status: required vs wagered (settled bets only)
-- ---------------------------------------------------------------------
create or replace function wager_status(p_user uuid)
returns table(required bigint, wagered bigint)
language sql stable as $$
  select
    (wd_setting_int('payments.wager_multiplier', 2) * coalesce((
        select sum(e.amount)
        from ledger_entries e join ledger_accounts a on a.id = e.account_id
        where a.owner_user_id = p_user and a.account_type = 'user_available'
          and e.kind in ('deposit','signup_grant','referral_reward','vip_reward')
          and e.amount > 0), 0))::bigint,
    coalesce((select sum(stake) from predictions
              where user_id = p_user and status in ('won','lost')), 0)::bigint
$$;

-- ---------------------------------------------------------------------
-- 4. withdrawals need the wager requirement met
-- ---------------------------------------------------------------------
create or replace function request_withdrawal(
  p_user uuid, p_symbol text, p_usd bigint, p_dest text, p_key text
) returns withdrawals language plpgsql as $$
declare u users%rowtype; ex withdrawals%rowtype; w withdrawals%rowtype;
        av uuid; hold uuid; aid uuid; used bigint; wid uuid := gen_random_uuid(); tx uuid := gen_random_uuid();
begin
  if not wd_setting_bool('payments.enabled', false) then raise exception 'payments_disabled_demo_only'; end if;
  select * into ex from withdrawals where user_id = p_user and idempotency_key = p_key;
  if found then return ex; end if;

  select * into u from users where id = p_user for update;
  if not found then raise exception 'user_not_found'; end if;
  if u.status <> 'active' then raise exception 'user_not_active'; end if;

  if exists (select 1 from wager_status(p_user) s where s.wagered < s.required) then
    raise exception 'wager_requirement_not_met';
  end if;

  select id into aid from assets where symbol = p_symbol and symbol in ('SOL','WIENER') and is_active;
  if aid is null then raise exception 'asset_not_supported'; end if;

  if p_usd < wd_setting_int('payments.min_withdraw', 5000000)
     or p_usd > wd_setting_int('payments.max_withdraw', 500000000) then
    raise exception 'withdraw_out_of_range';
  end if;
  select coalesce(sum(amount), 0) into used from withdrawals
   where user_id = p_user and status in ('pending','approved','sending','sent') and created_at > now() - interval '24 hours';
  if used + p_usd > wd_setting_int('payments.daily_withdraw_cap', 1000000000) then
    raise exception 'daily_withdraw_limit';
  end if;

  av := wd_user_account(p_user, 'user_available');
  hold := wd_user_account(p_user, 'user_withdrawing');

  insert into withdrawals(id, user_id, asset_id, amount, destination_ref, idempotency_key)
  values (wid, p_user, aid, p_usd, p_dest, p_key) returning * into w;

  begin
    insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
      (tx, av,   -p_usd, 'withdraw_hold', 'withdrawal', wid, 'wh:' || wid, 'Withdrawal requested'),
      (tx, hold,  p_usd, 'withdraw_hold', 'withdrawal', wid, 'wh:' || wid, 'Withdrawal requested');
  exception when check_violation then
    raise exception 'insufficient_balance';
  end;
  perform wd_audit(p_user, 'user', 'withdrawal.request', 'withdrawal', wid::text, null,
                   jsonb_build_object('usd', p_usd, 'asset', p_symbol, 'dest', p_dest), null);
  return w;
end $$;

-- ---------------------------------------------------------------------
-- 5. VIP + leaderboard: only SETTLED stakes count as wager
-- ---------------------------------------------------------------------
create or replace function update_vip(p_user uuid) returns integer
language plpgsql as $$
declare
  total bigint;
  t     vip_tiers%rowtype;
  n     integer := 0;
begin
  select coalesce(sum(stake), 0) into total
  from predictions where user_id = p_user and status in ('won', 'lost');

  for t in select * from vip_tiers where is_active and min_staked <= total order by sort_order loop
    insert into user_vip_status(user_id, tier_id) values (p_user, t.id)
    on conflict (user_id, tier_id) do nothing;
    if found then
      n := n + 1;
      if grant_credits(p_user, t.reward, 'vip_reward', 'vip:' || p_user || ':' || t.id, 'VIP reward: ' || t.name) then
        update user_vip_status set reward_paid = true where user_id = p_user and tier_id = t.id;
      end if;
    end if;
  end loop;
  return n;
end $$;

create or replace function leaderboard(
  p_metric text, p_since timestamptz, p_limit integer, p_offset integer
) returns table(rank bigint, user_id uuid, alias text, settled bigint, wins bigint,
                staked bigint, won_total bigint, accuracy_pct numeric)
language sql stable as $$
  with s as (
    select u.id as uid,
           left(coalesce(nullif(btrim(u.leaderboard_alias), ''), split_part(btrim(u.display_name), ' ', 1)), 32) as alias,
           count(*) filter (where p.status in ('won','lost'))                         as settled,
           count(*) filter (where p.status = 'won')                                   as wins,
           coalesce(sum(p.stake) filter (where p.status in ('won','lost')), 0)        as staked,
           coalesce(sum(p.payout_amount) filter (where p.status = 'won'), 0)          as won_total
    from users u
    join predictions p on p.user_id = u.id
    where not u.hide_on_leaderboard and u.status = 'active'
      and (p_since is null or p.created_at >= p_since)
    group by u.id, u.leaderboard_alias, u.display_name
  ), r as (
    select s.*, case when s.settled = 0 then null else round(100.0 * s.wins / s.settled, 2) end as acc
    from s
    where case when p_metric = 'accuracy'
               then s.settled >= wd_setting_int('leaderboard.min_settled', 1)
               else s.staked > 0 end
  )
  select row_number() over (
           order by (case when p_metric = 'accuracy' then r.acc else r.staked::numeric end) desc,
                    r.settled desc, r.uid
         ) as rank,
         r.uid, r.alias, r.settled, r.wins, r.staked, r.won_total, r.acc
  from r
  order by 1
  limit greatest(p_limit, 0) offset greatest(p_offset, 0)
$$;

-- ---------------------------------------------------------------------
-- 6. cashout: close an open prediction early at a server-computed amount.
--    The amount is computed by the backend from the live price (see services/cashout.py);
--    this function only enforces the money rules. Idempotent: a second call returns the same row.
--    Stake leaves 'reserved'; the amount lands in 'available'; the house takes the difference.
-- ---------------------------------------------------------------------
create or replace function cashout_prediction(p_user uuid, p_prediction uuid, p_amount bigint)
returns predictions language plpgsql as $$
declare
  p predictions%rowtype; m markets%rowtype; mid uuid;
  rs uuid; av uuid; house uuid; tx uuid := gen_random_uuid();
  cutoff bigint := wd_setting_int('cashout.cutoff_seconds', 300);
begin
  -- lock order: market first, then prediction (same as settle_market), so they cannot deadlock
  select market_id into mid from predictions where id = p_prediction and user_id = p_user;
  if mid is null then raise exception 'prediction_not_found'; end if;
  select * into m from markets where id = mid for share;

  select * into p from predictions where id = p_prediction and user_id = p_user for update;
  if p.status = 'cashed_out' then return p; end if;
  if p.status <> 'open' then raise exception 'prediction_already_final'; end if;

  if m.status not in ('open','paused','closed')
     or now() >= m.closes_at - make_interval(secs => cutoff)
     or p_amount is null or p_amount < 1 or p_amount > p.potential_payout then
    raise exception 'cashout_unavailable';
  end if;

  select id into rs from ledger_accounts where owner_user_id = p_user and account_type = 'user_reserved';
  select id into av from ledger_accounts where owner_user_id = p_user and account_type = 'user_available';
  select id into house from ledger_accounts where account_type = 'system_house' and owner_user_id is null;

  insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
    (tx, rs, -p.stake,  'cashout', 'prediction', p.id, 'cashout:' || p.id, 'Stake released (cashout)'),
    (tx, av,  p_amount, 'cashout', 'prediction', p.id, 'cashout:' || p.id, 'Cashout payout');
  if p.stake - p_amount <> 0 then
    insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo)
    values (tx, house, p.stake - p_amount, 'cashout', 'prediction', p.id, 'cashout:' || p.id, 'Cashout difference');
  end if;

  update predictions set status = 'cashed_out', payout_amount = p_amount, settled_at = now()
   where id = p.id returning * into p;

  perform wd_audit(p_user, 'user', 'prediction.cashout', 'prediction', p.id::text, null,
                   jsonb_build_object('stake', p.stake, 'cashout', p_amount), null);
  return p;
end $$;

-- keep browser roles locked out of the new functions
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on all functions in schema public from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on all functions in schema public from authenticated';
  end if;
end $$;

commit;