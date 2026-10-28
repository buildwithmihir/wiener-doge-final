begin;

-- ledger stays in USD base units (1 USD = 1,000,000). New kinds + accounts.
alter table ledger_entries drop constraint if exists ledger_entries_kind_check;
alter table ledger_entries add constraint ledger_entries_kind_check check (kind in (
  'signup_grant','stake_reserve','win_payout','loss_settle','refund','admin_adjustment',
  'referral_reward','vip_reward','deposit','withdraw_hold','withdraw_release','withdraw_sent'));

alter table ledger_accounts drop constraint if exists ledger_accounts_account_type_check;
alter table ledger_accounts add constraint ledger_accounts_account_type_check check (account_type in (
  'user_available','user_reserved','user_withdrawing','system_house','system_mint','system_fees','system_treasury'));
insert into ledger_accounts(account_type) values ('system_treasury') on conflict do nothing;

-- one deposit wallet per user (derived from a master seed; private keys are never stored).
-- Safe to drop only because nothing was live yet.
drop table if exists deposit_addresses;
create table deposit_addresses (
  user_id        uuid primary key references users(id) on delete restrict,
  owner_address  text not null unique,   -- receives SOL, and owns the WIENER token account
  token_account  text not null unique,   -- the WIENER associated token account
  sol_cursor     text,
  token_cursor   text,
  created_at     timestamptz not null default now()
);
alter table deposit_addresses enable row level security;

alter table deposits
  add column if not exists usd_value bigint,
  add column if not exists price     numeric(38,12);

alter table withdrawals
  add column if not exists idempotency_key text,
  add column if not exists tx_signature    text,
  add column if not exists reviewed_by     uuid references users(id) on delete set null,
  add column if not exists reviewed_reason text,
  add column if not exists sending_at      timestamptz,
  add column if not exists native_amount   bigint,        -- token base units actually sent
  add column if not exists native_decimals smallint,
  add column if not exists price           numeric(38,12), -- USD price used at send time
  add column if not exists updated_at      timestamptz not null default now();
create unique index if not exists uq_withdrawals_user_key on withdrawals(user_id, idempotency_key);
alter table withdrawals drop constraint if exists withdrawals_status_check;
alter table withdrawals add constraint withdrawals_status_check
  check (status in ('pending','approved','sending','rejected','sent','failed'));
-- withdrawals.amount = USD base units held from the user's balance

insert into application_settings(key, value, description) values
  ('payments.min_deposit',        '1000000',    'Min deposit credited, in USD base units ($1)'),
  ('payments.min_withdraw',       '5000000',    'Min withdrawal ($5)'),
  ('payments.max_withdraw',       '500000000',  'Max single withdrawal ($500)'),
  ('payments.daily_withdraw_cap', '1000000000', 'Max withdrawn per user per 24h ($1000)')
on conflict (key) do nothing;

drop function if exists credit_deposit(uuid, bigint, text, text);
drop function if exists request_withdrawal(uuid, bigint, text, text);

create or replace function wd_user_account(p_user uuid, p_type text) returns uuid
language plpgsql as $$
declare a uuid;
begin
  select id into a from ledger_accounts where owner_user_id = p_user and account_type = p_type;
  if a is null then
    insert into ledger_accounts(owner_user_id, account_type) values (p_user, p_type)
      on conflict (owner_user_id, account_type, currency) where owner_user_id is not null do nothing;
    select id into a from ledger_accounts where owner_user_id = p_user and account_type = p_type;
  end if;
  return a;
end $$;

-- credit one on-chain deposit, exactly once per (tx signature, asset)
create or replace function credit_deposit(
  p_user uuid, p_symbol text, p_amount bigint, p_usd bigint, p_price numeric, p_tx text
) returns boolean language plpgsql as $$
declare av uuid; tr uuid; aid uuid; ref text := p_tx || ':' || p_symbol; tx uuid := gen_random_uuid(); n integer;
begin
  if not wd_setting_bool('payments.enabled', false) then raise exception 'payments_disabled_demo_only'; end if;
  if p_amount <= 0 or p_usd <= 0 then return false; end if;
  select id into aid from assets where symbol = p_symbol and symbol in ('SOL','WIENER');
  if aid is null then raise exception 'asset_not_supported'; end if;
  av := wd_user_account(p_user, 'user_available');
  select id into tr from ledger_accounts where account_type = 'system_treasury' and owner_user_id is null;

  insert into deposits(user_id, asset_id, amount, chain, external_tx_ref, confirmations, status, verified_by, usd_value, price)
  values (p_user, aid, p_amount, 'solana', ref, 1, 'credited', 'rpc-finalized', p_usd, p_price)
  on conflict (chain, external_tx_ref) do nothing;
  get diagnostics n = row_count;
  if n = 0 then return false; end if;

  insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
    (tx, tr, -p_usd, 'deposit', 'user', p_user, 'dep:' || ref, 'Deposit ' || p_symbol),
    (tx, av,  p_usd, 'deposit', 'user', p_user, 'dep:' || ref, 'Deposit ' || p_symbol);
  perform wd_audit(p_user, 'system', 'deposit.credit', 'user', p_user::text, null,
                   jsonb_build_object('asset', p_symbol, 'native', p_amount, 'usd', p_usd, 'tx', p_tx), null);
  return true;
end $$;

-- user asks to withdraw p_usd (USD base units) as p_symbol: funds move available -> user_withdrawing
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

-- admin rejects: money returns to available
create or replace function reject_withdrawal(p_id uuid, p_actor uuid, p_reason text) returns void
language plpgsql as $$
declare w withdrawals%rowtype; av uuid; hold uuid; tx uuid := gen_random_uuid();
begin
  if p_reason is null or length(btrim(p_reason)) = 0 then raise exception 'reason_required'; end if;
  select * into w from withdrawals where id = p_id for update;
  if not found then raise exception 'withdrawal_not_found'; end if;
  if w.status not in ('pending','approved','failed') then raise exception 'withdraw_bad_state'; end if;
  av := wd_user_account(w.user_id, 'user_available');
  hold := wd_user_account(w.user_id, 'user_withdrawing');
  insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
    (tx, hold, -w.amount, 'withdraw_release', 'withdrawal', w.id, 'wr:' || w.id, 'Withdrawal rejected: refunded'),
    (tx, av,    w.amount, 'withdraw_release', 'withdrawal', w.id, 'wr:' || w.id, 'Withdrawal rejected: refunded');
  update withdrawals set status = 'rejected', reviewed_by = p_actor, reviewed_reason = p_reason, updated_at = now() where id = p_id;
  perform wd_audit(p_actor, 'admin', 'withdrawal.reject', 'withdrawal', p_id::text, null,
                   jsonb_build_object('usd', w.amount), p_reason);
end $$;

-- the on-chain transfer is final: release the hold against the treasury
create or replace function finalize_withdrawal(p_id uuid, p_sig text) returns void
language plpgsql as $$
declare w withdrawals%rowtype; hold uuid; tr uuid; tx uuid := gen_random_uuid();
begin
  select * into w from withdrawals where id = p_id for update;
  if not found then raise exception 'withdrawal_not_found'; end if;
  if w.status = 'sent' then return; end if;
  if w.status not in ('sending','approved') then raise exception 'withdraw_bad_state'; end if;
  hold := wd_user_account(w.user_id, 'user_withdrawing');
  select id into tr from ledger_accounts where account_type = 'system_treasury' and owner_user_id is null;
  insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
    (tx, hold, -w.amount, 'withdraw_sent', 'withdrawal', w.id, 'ws:' || w.id, 'Withdrawal sent'),
    (tx, tr,    w.amount, 'withdraw_sent', 'withdrawal', w.id, 'ws:' || w.id, 'Withdrawal sent');
  update withdrawals set status = 'sent', tx_signature = p_sig, updated_at = now() where id = p_id;
  perform wd_audit(null, 'system', 'withdrawal.sent', 'withdrawal', p_id::text, null,
                   jsonb_build_object('usd', w.amount, 'tx', p_sig), null);
end $$;

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