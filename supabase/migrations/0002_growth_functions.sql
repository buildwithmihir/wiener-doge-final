-- =====================================================================
-- WienerDoge | 0002_growth_functions.sql
-- Referral codes, referral attribution + rewards, VIP tiers, leaderboard.
-- All reward money goes through the append-only ledger (system_mint ->
-- user_available), idempotent by key. Demo credits only.
-- Run AFTER 0001_init_schema.sql.
-- =====================================================================

begin;

-- grant demo credits from the mint account (only for reward kinds)
create or replace function grant_credits(
  p_user uuid, p_amount bigint, p_kind text, p_key text, p_memo text
) returns boolean
language plpgsql as $$
declare
  av   uuid;
  mint uuid;
  tx   uuid := gen_random_uuid();
begin
  if p_kind not in ('referral_reward', 'vip_reward') then raise exception 'kind_not_allowed'; end if;
  if p_amount <= 0 then return false; end if;

  select id into av from ledger_accounts where owner_user_id = p_user and account_type = 'user_available';
  if av is null then raise exception 'user_not_found'; end if;

  if exists (select 1 from ledger_entries where idempotency_key = p_key and account_id = av) then
    return false;                                   -- already granted
  end if;

  select id into mint from ledger_accounts where account_type = 'system_mint' and owner_user_id is null;
  insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
    (tx, mint, -p_amount, p_kind, 'user', p_user, p_key, p_memo),
    (tx, av,    p_amount, p_kind, 'user', p_user, p_key, p_memo);
  return true;
end $$;

-- unique referral code for a user (idempotent)
create or replace function ensure_referral_code(p_user uuid) returns text
language plpgsql as $$
declare
  c text;
  tries integer := 0;
begin
  select code into c from referral_codes where user_id = p_user;
  if found then return c; end if;
  loop
    c := upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8));
    begin
      insert into referral_codes(user_id, code) values (p_user, c);
      return c;
    exception when unique_violation then
      select code into c from referral_codes where user_id = p_user;
      if found then return c; end if;
      tries := tries + 1;
      if tries > 10 then raise exception 'referral_code_generation_failed'; end if;
    end;
  end loop;
end $$;

-- VIP: unlock every tier whose threshold is reached; pay each reward once
create or replace function update_vip(p_user uuid) returns integer
language plpgsql as $$
declare
  total bigint;
  t     vip_tiers%rowtype;
  n     integer := 0;
begin
  select coalesce(sum(stake), 0) into total
  from predictions where user_id = p_user and status in ('open', 'won', 'lost');

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

-- referral attribution: strict rules, every rejection has a code
create or replace function apply_referral(p_referred uuid, p_code text) returns referrals
language plpgsql as $$
declare
  rc  referral_codes%rowtype;
  r   referrals%rowtype;
begin
  select * into rc from referral_codes where code = upper(btrim(p_code));
  if not found then raise exception 'invalid_code'; end if;
  if rc.user_id = p_referred then raise exception 'self_referral'; end if;
  if exists (select 1 from referrals where referred_id = p_referred) then raise exception 'already_referred'; end if;
  if exists (select 1 from predictions where user_id = p_referred) then raise exception 'too_late_existing_user'; end if;
  if exists (select 1 from referrals where referrer_id = p_referred and referred_id = rc.user_id) then
    raise exception 'circular_referral';
  end if;
  if (select status from users where id = rc.user_id) <> 'active' then raise exception 'referrer_not_active'; end if;

  insert into referrals(referrer_id, referred_id, code_id) values (rc.user_id, p_referred, rc.id) returning * into r;
  perform wd_audit(p_referred, 'user', 'referral.apply', 'referral', r.id::text, null, to_jsonb(r), null);
  return r;
end $$;

-- pay referral rewards once the referred user has really played (called by worker)
create or replace function process_referral_rewards() returns integer
language plpgsql as $$
declare
  r        referrals%rowtype;
  need     bigint := wd_setting_int('referral.min_predictions', 1);
  reward   bigint := wd_setting_int('referral.reward', 0);
  cap      bigint := wd_setting_int('referral.max_rewards_per_user', 50);
  n        integer := 0;
begin
  for r in select * from referrals where status = 'pending' order by created_at for update skip locked loop
    if (select count(*) from predictions where user_id = r.referred_id) < need then
      continue;
    end if;
    if (select status from users where id = r.referred_id) <> 'active'
       or (select status from users where id = r.referrer_id) <> 'active' then
      update referrals set status = 'rejected', reject_reason = 'account_not_active' where id = r.id;
      continue;
    end if;
    if (select count(*) from referrals where referrer_id = r.referrer_id and status = 'rewarded') >= cap then
      update referrals set status = 'rejected', reject_reason = 'reward_cap_reached' where id = r.id;
      continue;
    end if;
    perform grant_credits(r.referrer_id, reward, 'referral_reward', 'ref:' || r.id, 'Referral reward');
    update referrals set status = 'rewarded', reward_amount = reward, rewarded_at = now() where id = r.id;
    n := n + 1;
  end loop;
  return n;
end $$;

-- leaderboard: deterministic (metric desc, settled desc, user id), privacy-aware alias
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
           coalesce(sum(p.stake) filter (where p.status in ('open','won','lost')), 0) as staked,
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

insert into application_settings(key, value, description) values
  ('referral.max_rewards_per_user', '50', 'Max rewarded referrals per referrer'),
  ('settlement.void_after_seconds', '21600', 'If no valid settlement price exists this long after close, void the market and refund')
on conflict (key) do nothing;

-- keep browser roles locked out of the new functions too
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
