begin;

-- settings -------------------------------------------------------------
insert into application_settings(key, value, description) values
  ('referral.reward',    '5000000',   'Referral reward in USD base units ($5)'),
  ('referral.min_wager', '200000000', 'Referred user must wager this much on SETTLED bets ($200) before the referrer is paid'),
  ('price.stale_after_seconds', '900', 'Worker polls every ~10 min, so a price stays fresh for 15 min'),
  ('price.reopen_after_healthy_checks', '2', 'Healthy checks in a row before an auto-paused market reopens'),
  ('price.max_move_bps_per_check.wiener', '5000', 'WIENER is volatile: allow 50% between two checks')
on conflict (key) do update set value = excluded.value;

-- how much a user has wagered on SETTLED bets (cashed-out / open / refunded never count)
create or replace function referral_wagered(p_user uuid) returns bigint
language sql stable as $$
  select coalesce(sum(stake), 0)::bigint from predictions where user_id = p_user and status in ('won','lost')
$$;

-- reward only after the referred user has wagered referral.min_wager ($200) on settled bets
create or replace function process_referral_rewards() returns integer
language plpgsql as $$
declare
  r         referrals%rowtype;
  need_bets bigint := wd_setting_int('referral.min_predictions', 1);
  need_wag  bigint := wd_setting_int('referral.min_wager', 200000000);
  reward    bigint := wd_setting_int('referral.reward', 0);
  cap       bigint := wd_setting_int('referral.max_rewards_per_user', 50);
  n         integer := 0;
begin
  for r in select * from referrals where status = 'pending' order by created_at for update skip locked loop
    if (select count(*) from predictions where user_id = r.referred_id) < need_bets then
      continue;
    end if;
    if referral_wagered(r.referred_id) < need_wag then
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

-- reopen markets that the SYSTEM paused (admin pauses stay paused)
update markets set status = 'open', pause_reason = null
 where status = 'paused' and pause_reason like 'auto:%' and betting_closes_at > now();

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