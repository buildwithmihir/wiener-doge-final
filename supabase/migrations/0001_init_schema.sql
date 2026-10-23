-- =====================================================================
-- WienerDoge  |  0001_init_schema.sql
-- Demo-credit prediction markets. Money = BIGINT base units
-- (1 DEMO = 1,000,000 units). No floats anywhere.
-- Run once on a fresh Supabase project (SQL Editor) or via psql.
-- Backend connects with the server-side DB role only; the browser never
-- talks to the database (RLS enabled, no policies => deny-all for
-- anon/authenticated).
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------
create or replace function wd_set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ---------------------------------------------------------------------
-- 1. users
-- ---------------------------------------------------------------------
create table users (
  id                   uuid primary key default gen_random_uuid(),
  telegram_id          bigint not null unique,
  username             text check (username is null or length(username) between 1 and 64),
  display_name         text not null check (length(btrim(display_name)) between 1 and 128),
  leaderboard_alias    text check (leaderboard_alias is null or length(btrim(leaderboard_alias)) between 1 and 32),
  hide_on_leaderboard  boolean not null default false,
  photo_url            text,
  language_code        text,
  status               text not null default 'active' check (status in ('active','suspended','banned')),
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  last_seen_at         timestamptz
);
create trigger trg_users_updated before update on users
  for each row execute function wd_set_updated_at();
comment on table users is 'Telegram users. No phone/email stored. Retention: anonymise (blank names) on deletion request; never hard-delete (ledger FK).';

-- ---------------------------------------------------------------------
-- 2. user_roles
-- ---------------------------------------------------------------------
create table user_roles (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references users(id) on delete cascade,
  role        text not null check (role in ('user','moderator','admin')),
  granted_by  uuid references users(id) on delete set null,
  created_at  timestamptz not null default now(),
  unique (user_id, role)
);
create index idx_user_roles_role on user_roles(role);

-- ---------------------------------------------------------------------
-- 3. assets
-- ---------------------------------------------------------------------
create table assets (
  id                   uuid primary key default gen_random_uuid(),
  symbol               text not null unique check (symbol = upper(symbol) and length(symbol) between 1 and 16),
  name                 text not null,
  decimals             smallint not null default 9 check (decimals between 0 and 18),
  is_prediction_asset  boolean not null default false,
  is_active            boolean not null default true,
  provider_key         text,
  provider_ref         text,
  created_at           timestamptz not null default now()
);
comment on column assets.is_prediction_asset is 'USDC is NOT a prediction asset unless an admin explicitly enables it.';

-- ---------------------------------------------------------------------
-- 18. application_settings (created early; functions read it)
-- ---------------------------------------------------------------------
create table application_settings (
  key          text primary key check (key ~ '^[a-z0-9_.]+$'),
  value        jsonb not null,
  description  text,
  updated_by   uuid references users(id) on delete set null,
  updated_at   timestamptz not null default now()
);
create trigger trg_settings_updated before update on application_settings
  for each row execute function wd_set_updated_at();

create or replace function wd_setting_int(p_key text, p_default bigint) returns bigint
language sql stable as $$
  select coalesce((select (value #>> '{}')::bigint from application_settings where key = p_key), p_default)
$$;

create or replace function wd_setting_bool(p_key text, p_default boolean) returns boolean
language sql stable as $$
  select coalesce((select (value #>> '{}')::boolean from application_settings where key = p_key), p_default)
$$;

-- ---------------------------------------------------------------------
-- 4. markets
-- ---------------------------------------------------------------------
create table markets (
  id                   uuid primary key default gen_random_uuid(),
  asset_id             uuid not null references assets(id) on delete restrict,
  duration_seconds     integer not null check (duration_seconds in (86400, 172800, 604800, 2592000)),
  target_price         numeric(38,12) not null check (target_price > 0),
  opens_at             timestamptz not null,
  betting_closes_at    timestamptz not null,
  closes_at            timestamptz not null,
  status               text not null default 'draft'
                       check (status in ('draft','open','paused','closed','settling','settled','voided')),
  payout_bps           integer not null default 18000 check (payout_bps > 10000 and payout_bps <= 100000),
  min_stake            bigint not null default 1000000 check (min_stake > 0),
  max_stake            bigint not null default 1000000000 check (max_stake >= min_stake),
  terms_version        integer not null default 1,
  pause_reason         text,
  created_by           uuid references users(id) on delete set null,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  check (opens_at < betting_closes_at and betting_closes_at <= closes_at),
  unique (asset_id, duration_seconds, target_price, closes_at)
);
create index idx_markets_status_closes on markets(status, closes_at);
create index idx_markets_asset_status on markets(asset_id, status);
comment on column markets.payout_bps is 'SIMULATED payout multiplier in basis points (18000 = 1.8x stake). Demo credits only.';
comment on column markets.betting_closes_at is 'No new predictions accepted at/after this instant (enforced in place_prediction + insert trigger).';
comment on column markets.closes_at is 'Settlement reference time. Rule: price >= target => ABOVE wins, price < target => BELOW wins (a tie goes to ABOVE).';

create or replace function wd_markets_guard() returns trigger
language plpgsql as $$
declare
  t text;
begin
  if tg_op = 'INSERT' then
    if new.status not in ('draft','open') then
      raise exception 'market_must_start_draft_or_open';
    end if;
    if new.status = 'open' and new.betting_closes_at <= now() then
      raise exception 'market_already_closed_for_betting';
    end if;
    return new;
  end if;

  -- UPDATE
  if old.status in ('settled','voided') then
    raise exception 'market_final_state_immutable';
  end if;

  if old.status <> 'draft' and (
       new.asset_id <> old.asset_id
    or new.duration_seconds <> old.duration_seconds
    or new.target_price <> old.target_price
    or new.opens_at <> old.opens_at
    or new.betting_closes_at <> old.betting_closes_at
    or new.closes_at <> old.closes_at
    or new.payout_bps <> old.payout_bps
    or new.min_stake <> old.min_stake
    or new.max_stake <> old.max_stake
  ) then
    raise exception 'market_terms_immutable_after_draft';
  end if;

  if new.status <> old.status then
    t := old.status || '>' || new.status;
    if not (t = any (array[
        'draft>open','draft>voided',
        'open>paused','paused>open',
        'open>closed','paused>closed',
        'closed>settling','settling>settled',
        'open>settled','paused>settled','closed>settled',
        'open>voided','paused>voided','closed>voided','settling>voided'
    ])) then
      raise exception 'illegal_market_transition: %', t;
    end if;
    if t in ('draft>open','paused>open') and now() >= new.betting_closes_at then
      raise exception 'cannot_open_after_betting_closes';
    end if;
  end if;

  new.updated_at := now();
  return new;
end $$;
create trigger trg_markets_guard before insert or update on markets
  for each row execute function wd_markets_guard();

-- ---------------------------------------------------------------------
-- market_config_versions (extra) — every market change is versioned
-- ---------------------------------------------------------------------
create table market_config_versions (
  id          bigserial primary key,
  market_id   uuid not null references markets(id) on delete cascade,
  version     integer not null,
  config      jsonb not null,
  changed_by  uuid references users(id) on delete set null,
  reason      text,
  created_at  timestamptz not null default now(),
  unique (market_id, version)
);

create or replace function wd_markets_version() returns trigger
language plpgsql as $$
declare
  v integer;
  actor uuid;
begin
  select coalesce(max(version), 0) + 1 into v from market_config_versions where market_id = new.id;
  begin
    actor := nullif(current_setting('wd.actor', true), '')::uuid;
  exception when others then
    actor := null;
  end;
  insert into market_config_versions(market_id, version, config, changed_by, reason)
  values (new.id, v, to_jsonb(new), actor, nullif(current_setting('wd.reason', true), ''));
  return new;
end $$;
create trigger trg_markets_version after insert or update on markets
  for each row execute function wd_markets_version();

-- ---------------------------------------------------------------------
-- 5. market_price_snapshots
-- ---------------------------------------------------------------------
create table market_price_snapshots (
  id          bigserial primary key,
  asset_id    uuid not null references assets(id) on delete restrict,
  price       numeric(38,12) not null check (price > 0),
  source      text not null,
  fetched_at  timestamptz not null,
  is_stale    boolean not null default false,
  is_anomalous boolean not null default false,
  raw         jsonb,
  created_at  timestamptz not null default now(),
  unique (asset_id, source, fetched_at)
);
create index idx_snap_asset_time on market_price_snapshots(asset_id, fetched_at desc);
comment on table market_price_snapshots is 'Only real provider data. Never insert invented prices. Retention: keep 90d at full resolution, downsample older (job).';

-- ---------------------------------------------------------------------
-- 8. ledger_accounts
-- ---------------------------------------------------------------------
create table ledger_accounts (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid references users(id) on delete restrict,
  account_type   text not null check (account_type in
                   ('user_available','user_reserved','system_house','system_mint','system_fees')),
  currency       text not null default 'DEMO' check (currency = 'DEMO'),
  balance        bigint not null default 0,
  created_at     timestamptz not null default now(),
  check (
    (left(account_type, 5) = 'user_'   and owner_user_id is not null and balance >= 0) or
    (left(account_type, 7) = 'system_' and owner_user_id is null)
  )
);
create unique index uq_ledger_acct_user on ledger_accounts(owner_user_id, account_type, currency)
  where owner_user_id is not null;
create unique index uq_ledger_acct_system on ledger_accounts(account_type, currency)
  where owner_user_id is null;
comment on column ledger_accounts.balance is 'Cache maintained ONLY by the ledger_entries trigger. Direct updates are rejected. Verified by ledger_reconcile().';

create or replace function wd_ledger_accounts_guard() returns trigger
language plpgsql as $$
begin
  if new.balance is distinct from old.balance
     and coalesce(current_setting('wd.ledger_write', true), 'off') <> 'on' then
    raise exception 'balance_is_ledger_managed';
  end if;
  if new.owner_user_id is distinct from old.owner_user_id
     or new.account_type is distinct from old.account_type then
    raise exception 'ledger_account_identity_immutable';
  end if;
  return new;
end $$;
create trigger trg_ledger_accounts_guard before update on ledger_accounts
  for each row execute function wd_ledger_accounts_guard();

-- ---------------------------------------------------------------------
-- 9. ledger_entries (append-only, signed, double-entry per tx_id)
-- ---------------------------------------------------------------------
create table ledger_entries (
  id               bigserial primary key,
  tx_id            uuid not null,
  account_id       uuid not null references ledger_accounts(id) on delete restrict,
  amount           bigint not null check (amount <> 0),
  kind             text not null check (kind in
                     ('signup_grant','stake_reserve','win_payout','loss_settle','refund',
                      'admin_adjustment','referral_reward','vip_reward')),
  ref_type         text,
  ref_id           uuid,
  idempotency_key  text not null check (length(idempotency_key) between 1 and 200),
  memo             text,
  created_at       timestamptz not null default now(),
  unique (idempotency_key, account_id)
);
create index idx_ledger_entries_account on ledger_entries(account_id, id desc);
create index idx_ledger_entries_tx on ledger_entries(tx_id);
create index idx_ledger_entries_ref on ledger_entries(ref_type, ref_id);
comment on table ledger_entries is 'Append-only. Positive = credit to account, negative = debit. Sum per tx_id must be 0 (checked at commit). Never delete; retain forever.';

create or replace function wd_ledger_entries_apply() returns trigger
language plpgsql as $$
begin
  perform set_config('wd.ledger_write', 'on', true);
  update ledger_accounts set balance = balance + new.amount where id = new.account_id;
  perform set_config('wd.ledger_write', 'off', true);
  return new;
end $$;
create trigger trg_ledger_entries_apply before insert on ledger_entries
  for each row execute function wd_ledger_entries_apply();

create or replace function wd_ledger_entries_block() returns trigger
language plpgsql as $$
begin
  raise exception 'ledger_is_append_only';
end $$;
create trigger trg_ledger_entries_noupd before update or delete on ledger_entries
  for each row execute function wd_ledger_entries_block();
create trigger trg_ledger_entries_notrunc before truncate on ledger_entries
  for each statement execute function wd_ledger_entries_block();

create or replace function wd_ledger_check_balanced() returns trigger
language plpgsql as $$
declare
  s bigint;
begin
  select coalesce(sum(amount), 0) into s from ledger_entries where tx_id = new.tx_id;
  if s <> 0 then
    raise exception 'ledger_tx_unbalanced: tx=% sum=%', new.tx_id, s;
  end if;
  return null;
end $$;
create constraint trigger trg_ledger_tx_balanced after insert on ledger_entries
  deferrable initially deferred for each row execute function wd_ledger_check_balanced();

-- system accounts
insert into ledger_accounts(account_type) values ('system_house'), ('system_mint'), ('system_fees');

-- ---------------------------------------------------------------------
-- 6. predictions
-- ---------------------------------------------------------------------
create table predictions (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references users(id) on delete restrict,
  market_id              uuid not null references markets(id) on delete restrict,
  direction              text not null check (direction in ('above','below')),
  stake                  bigint not null check (stake > 0),
  payout_bps_snapshot    integer not null check (payout_bps_snapshot > 10000),
  target_price_snapshot  numeric(38,12) not null check (target_price_snapshot > 0),
  closes_at_snapshot     timestamptz not null,
  potential_payout       bigint not null check (potential_payout >= stake),
  status                 text not null default 'open' check (status in ('open','won','lost','refunded')),
  payout_amount          bigint not null default 0 check (payout_amount >= 0),
  idempotency_key        text not null check (length(idempotency_key) between 8 and 120),
  created_at             timestamptz not null default now(),
  settled_at             timestamptz,
  unique (user_id, idempotency_key)
);
create index idx_pred_user_time on predictions(user_id, created_at desc);
create index idx_pred_market_status on predictions(market_id, status);
comment on column predictions.target_price_snapshot is 'Terms frozen at confirmation. Immutable by trigger.';

create or replace function wd_predictions_guard() returns trigger
language plpgsql as $$
declare
  m markets%rowtype;
begin
  if tg_op = 'DELETE' then
    raise exception 'predictions_are_permanent';
  end if;

  if tg_op = 'INSERT' then
    select * into m from markets where id = new.market_id;
    if not found then raise exception 'market_not_found'; end if;
    if m.status <> 'open' then raise exception 'market_not_open'; end if;
    if now() < m.opens_at then raise exception 'market_not_started'; end if;
    if now() >= m.betting_closes_at then raise exception 'betting_closed'; end if;
    if new.stake < m.min_stake or new.stake > m.max_stake then raise exception 'stake_out_of_range'; end if;
    if new.target_price_snapshot <> m.target_price
       or new.payout_bps_snapshot <> m.payout_bps
       or new.closes_at_snapshot <> m.closes_at then
      raise exception 'terms_mismatch';
    end if;
    return new;
  end if;

  -- UPDATE: only status / payout_amount / settled_at may change, and only out of 'open'
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
create trigger trg_predictions_guard before insert or update or delete on predictions
  for each row execute function wd_predictions_guard();

-- ---------------------------------------------------------------------
-- 7. settlements
-- ---------------------------------------------------------------------
create table settlements (
  id            uuid primary key default gen_random_uuid(),
  market_id     uuid not null unique references markets(id) on delete restrict,
  result        text not null check (result in ('above','below','void')),
  snapshot_id   bigint references market_price_snapshots(id) on delete restrict,
  settle_price  numeric(38,12),
  rule          text not null,
  reason        text,
  settled_by    uuid references users(id) on delete set null,
  predictions_settled integer not null default 0,
  created_at    timestamptz not null default now(),
  check ((result = 'void' and snapshot_id is null and settle_price is null)
      or (result <> 'void' and snapshot_id is not null and settle_price is not null))
);

-- ---------------------------------------------------------------------
-- 17. audit_logs (append-only)
-- ---------------------------------------------------------------------
create table audit_logs (
  id             bigserial primary key,
  actor_user_id  uuid references users(id) on delete set null,
  actor_type     text not null check (actor_type in ('user','admin','system','bot')),
  action         text not null,
  entity_type    text not null,
  entity_id      text,
  before_data    jsonb,
  after_data     jsonb,
  reason         text,
  created_at     timestamptz not null default now(),
  check (actor_type <> 'admin' or (reason is not null and length(btrim(reason)) > 0))
);
create index idx_audit_entity on audit_logs(entity_type, entity_id);
create index idx_audit_actor_time on audit_logs(actor_user_id, created_at desc);
comment on table audit_logs is 'Append-only. Admin actions REQUIRE a reason. Retain >= 2 years.';

create or replace function wd_audit_block() returns trigger
language plpgsql as $$
begin
  raise exception 'audit_log_is_append_only';
end $$;
create trigger trg_audit_noupd before update or delete on audit_logs
  for each row execute function wd_audit_block();
create trigger trg_audit_notrunc before truncate on audit_logs
  for each statement execute function wd_audit_block();

create or replace function wd_audit(
  p_actor uuid, p_actor_type text, p_action text, p_entity_type text,
  p_entity_id text, p_before jsonb, p_after jsonb, p_reason text
) returns void language sql as $$
  insert into audit_logs(actor_user_id, actor_type, action, entity_type, entity_id, before_data, after_data, reason)
  values (p_actor, p_actor_type, p_action, p_entity_type, p_entity_id, p_before, p_after, p_reason)
$$;

-- ---------------------------------------------------------------------
-- admin_approvals (extra)
-- ---------------------------------------------------------------------
create table admin_approvals (
  id            uuid primary key default gen_random_uuid(),
  action        text not null,
  payload       jsonb not null default '{}'::jsonb,
  reason        text not null check (length(btrim(reason)) > 0),
  status        text not null default 'pending' check (status in ('pending','approved','rejected')),
  requested_by  uuid not null references users(id) on delete restrict,
  decided_by    uuid references users(id) on delete restrict,
  created_at    timestamptz not null default now(),
  decided_at    timestamptz,
  check (decided_by is null or decided_by <> requested_by)
);

-- ---------------------------------------------------------------------
-- 10/11. deposits & withdrawals — DISABLED (insert blocked by setting)
-- ---------------------------------------------------------------------
create table deposits (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references users(id) on delete restrict,
  asset_id          uuid not null references assets(id) on delete restrict,
  amount            bigint not null check (amount > 0),
  chain             text not null,
  external_tx_ref   text not null,
  confirmations     integer not null default 0 check (confirmations >= 0),
  status            text not null default 'pending' check (status in ('pending','confirmed','rejected','credited')),
  verified_by       text,
  created_at        timestamptz not null default now(),
  unique (chain, external_tx_ref)
);
create table withdrawals (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references users(id) on delete restrict,
  asset_id         uuid not null references assets(id) on delete restrict,
  amount           bigint not null check (amount > 0),
  destination_ref  text not null,
  status           text not null default 'pending' check (status in ('pending','approved','rejected','sent','failed')),
  approval_id      uuid references admin_approvals(id) on delete restrict,
  created_at       timestamptz not null default now()
);
create index idx_deposits_user on deposits(user_id, created_at desc);
create index idx_withdrawals_user on withdrawals(user_id, created_at desc);

create or replace function wd_payments_disabled() returns trigger
language plpgsql as $$
begin
  if not wd_setting_bool('payments.enabled', false) then
    raise exception 'payments_disabled_demo_only';
  end if;
  return new;
end $$;
create trigger trg_deposits_disabled before insert on deposits
  for each row execute function wd_payments_disabled();
create trigger trg_withdrawals_disabled before insert on withdrawals
  for each row execute function wd_payments_disabled();
comment on table deposits is 'DISABLED in v1: inserts blocked until payments.enabled=true after separate legal/security review. A client-supplied signature is never proof.';

-- ---------------------------------------------------------------------
-- 12/13. referrals
-- ---------------------------------------------------------------------
create table referral_codes (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null unique references users(id) on delete cascade,
  code        text not null unique check (code ~ '^[A-Z0-9]{6,16}$'),
  created_at  timestamptz not null default now()
);
create table referrals (
  id             uuid primary key default gen_random_uuid(),
  referrer_id    uuid not null references users(id) on delete restrict,
  referred_id    uuid not null unique references users(id) on delete restrict,
  code_id        uuid not null references referral_codes(id) on delete restrict,
  status         text not null default 'pending' check (status in ('pending','eligible','rewarded','rejected')),
  reward_amount  bigint not null default 0 check (reward_amount >= 0),
  reject_reason  text,
  rewarded_at    timestamptz,
  created_at     timestamptz not null default now(),
  check (referrer_id <> referred_id)
);
create index idx_referrals_referrer on referrals(referrer_id, status);

-- ---------------------------------------------------------------------
-- 14/15. VIP
-- ---------------------------------------------------------------------
create table vip_tiers (
  id           smallserial primary key,
  name         text not null unique,
  min_staked   bigint not null unique check (min_staked >= 0),
  reward       bigint not null default 0 check (reward >= 0),
  sort_order   integer not null unique,
  benefits     jsonb not null default '[]'::jsonb,
  is_active    boolean not null default true
);
create table user_vip_status (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references users(id) on delete cascade,
  tier_id      smallint not null references vip_tiers(id) on delete restrict,
  achieved_at  timestamptz not null default now(),
  reward_paid  boolean not null default false,
  unique (user_id, tier_id)
);
create index idx_vip_user on user_vip_status(user_id, achieved_at desc);

-- ---------------------------------------------------------------------
-- 16. notifications (+ preferences)
-- ---------------------------------------------------------------------
create table notifications (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references users(id) on delete cascade,
  type        text not null,
  title       text not null,
  body        text not null,
  payload     jsonb not null default '{}'::jsonb,
  dedupe_key  text unique,
  status      text not null default 'pending' check (status in ('pending','sent','failed')),
  attempts    integer not null default 0,
  sent_at     timestamptz,
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);
create index idx_notif_user on notifications(user_id, created_at desc);
create index idx_notif_pending on notifications(status, created_at) where status = 'pending';
create table notification_preferences (
  user_id          uuid primary key references users(id) on delete cascade,
  market_results   boolean not null default true,
  market_closing   boolean not null default true,
  referrals        boolean not null default true,
  vip              boolean not null default true,
  updated_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- extras: idempotency, provider health, background jobs
-- ---------------------------------------------------------------------
create table idempotency_records (
  id            bigserial primary key,
  scope         text not null,
  key           text not null,
  request_hash  text not null,
  response      jsonb,
  created_at    timestamptz not null default now(),
  expires_at    timestamptz not null default now() + interval '2 days',
  unique (scope, key)
);
create index idx_idem_expires on idempotency_records(expires_at);

create table provider_health_history (
  id             bigserial primary key,
  provider_key   text not null,
  asset_id       uuid references assets(id) on delete cascade,
  status         text not null check (status in ('healthy','stale','missing','anomalous','error')),
  latency_ms     integer,
  last_price_at  timestamptz,
  detail         text,
  checked_at     timestamptz not null default now()
);
create index idx_provider_health on provider_health_history(provider_key, checked_at desc);

create table background_jobs (
  id            uuid primary key default gen_random_uuid(),
  job_key       text not null,
  dedupe_key    text unique,
  status        text not null default 'queued' check (status in ('queued','running','done','failed')),
  attempts      integer not null default 0,
  run_at        timestamptz not null default now(),
  locked_until  timestamptz,
  last_error    text,
  payload       jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now(),
  finished_at   timestamptz
);
create index idx_jobs_due on background_jobs(status, run_at);

-- ---------------------------------------------------------------------
-- user bootstrap: accounts + signup grant + notification prefs
-- ---------------------------------------------------------------------
create or replace function wd_user_bootstrap() returns trigger
language plpgsql as $$
declare
  grant_amt bigint;
  av uuid;
  mint uuid;
  tx uuid := gen_random_uuid();
begin
  insert into ledger_accounts(owner_user_id, account_type) values (new.id, 'user_available') returning id into av;
  insert into ledger_accounts(owner_user_id, account_type) values (new.id, 'user_reserved');
  insert into notification_preferences(user_id) values (new.id);

  grant_amt := wd_setting_int('wallet.signup_grant', 0);
  if grant_amt > 0 then
    select id into mint from ledger_accounts where account_type = 'system_mint' and owner_user_id is null;
    insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
      (tx, mint, -grant_amt, 'signup_grant', 'user', new.id, 'signup:' || new.id, 'Demo credits welcome grant'),
      (tx, av,    grant_amt, 'signup_grant', 'user', new.id, 'signup:' || new.id, 'Demo credits welcome grant');
  end if;
  return new;
end $$;
create trigger trg_users_bootstrap after insert on users
  for each row execute function wd_user_bootstrap();

-- ---------------------------------------------------------------------
-- core operations (atomic, idempotent, safe to retry)
-- ---------------------------------------------------------------------

-- place a prediction: reserve stake + insert prediction in ONE transaction
create or replace function place_prediction(
  p_user uuid, p_market uuid, p_direction text, p_stake bigint, p_key text
) returns predictions
language plpgsql as $$
declare
  u      users%rowtype;
  m      markets%rowtype;
  ex     predictions%rowtype;
  pred   predictions%rowtype;
  av     uuid;
  rs     uuid;
  tx     uuid := gen_random_uuid();
  pid    uuid := gen_random_uuid();
begin
  select * into ex from predictions where user_id = p_user and idempotency_key = p_key;
  if found then return ex; end if;

  select * into u from users where id = p_user;
  if not found then raise exception 'user_not_found'; end if;
  if u.status <> 'active' then raise exception 'user_not_active'; end if;

  select * into m from markets where id = p_market for share;
  if not found then raise exception 'market_not_found'; end if;

  select id into av from ledger_accounts where owner_user_id = p_user and account_type = 'user_available';
  select id into rs from ledger_accounts where owner_user_id = p_user and account_type = 'user_reserved';

  begin
    insert into predictions(id, user_id, market_id, direction, stake, payout_bps_snapshot,
                            target_price_snapshot, closes_at_snapshot, potential_payout, idempotency_key)
    values (pid, p_user, p_market, p_direction, p_stake, m.payout_bps, m.target_price, m.closes_at,
            greatest(p_stake, (p_stake * m.payout_bps) / 10000), p_key)
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

-- settle using a real, fresh, non-anomalous snapshot taken at/after close
create or replace function settle_market(p_market uuid, p_snapshot bigint, p_actor uuid default null)
returns settlements
language plpgsql as $$
declare
  m       markets%rowtype;
  s       market_price_snapshots%rowtype;
  st      settlements%rowtype;
  res     text;
  p       predictions%rowtype;
  house   uuid;
  rs      uuid;
  av      uuid;
  tx      uuid;
  win_amt bigint;
  cnt     integer := 0;
  max_delay bigint := wd_setting_int('settlement.max_snapshot_delay_seconds', 300);
begin
  select * into m from markets where id = p_market for update;
  if not found then raise exception 'market_not_found'; end if;

  select * into st from settlements where market_id = p_market;
  if found then return st; end if;                 -- idempotent retry

  if m.status in ('draft','voided') then raise exception 'market_not_settleable'; end if;
  if now() < m.closes_at then raise exception 'market_not_closed_yet'; end if;

  select * into s from market_price_snapshots where id = p_snapshot;
  if not found then raise exception 'price_unavailable'; end if;
  if s.asset_id <> m.asset_id then raise exception 'snapshot_wrong_asset'; end if;
  if s.is_stale or s.is_anomalous then raise exception 'snapshot_unreliable'; end if;
  if s.fetched_at < m.closes_at or s.fetched_at > m.closes_at + make_interval(secs => max_delay) then
    raise exception 'snapshot_outside_settlement_window';
  end if;

  res := case when s.price >= m.target_price then 'above' else 'below' end;

  select id into house from ledger_accounts where account_type = 'system_house' and owner_user_id is null;

  for p in select * from predictions where market_id = p_market and status = 'open' order by id for update loop
    select id into rs from ledger_accounts where owner_user_id = p.user_id and account_type = 'user_reserved';
    select id into av from ledger_accounts where owner_user_id = p.user_id and account_type = 'user_available';
    tx := gen_random_uuid();

    if p.direction = res then
      win_amt := p.potential_payout;
      insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo)
      values (tx, rs, -p.stake, 'win_payout', 'prediction', p.id, 'settle:' || p.id, 'Stake released (won)'),
             (tx, av,  win_amt, 'win_payout', 'prediction', p.id, 'settle:' || p.id, 'Simulated winnings');
      if win_amt - p.stake > 0 then
        insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo)
        values (tx, house, -(win_amt - p.stake), 'win_payout', 'prediction', p.id, 'settle:' || p.id, 'Simulated profit funded by house');
      end if;
      update predictions set status = 'won', payout_amount = win_amt, settled_at = now() where id = p.id;
    else
      insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo)
      values (tx, rs,    -p.stake, 'loss_settle', 'prediction', p.id, 'settle:' || p.id, 'Stake forfeited (lost)'),
             (tx, house,  p.stake, 'loss_settle', 'prediction', p.id, 'settle:' || p.id, 'Stake forfeited (lost)');
      update predictions set status = 'lost', payout_amount = 0, settled_at = now() where id = p.id;
    end if;
    cnt := cnt + 1;
  end loop;

  insert into settlements(market_id, result, snapshot_id, settle_price, rule, settled_by, predictions_settled)
  values (p_market, res, s.id, s.price, 'price>=target => above; price<target => below', p_actor, cnt)
  returning * into st;

  update markets set status = 'settled' where id = p_market;
  perform wd_audit(p_actor, case when p_actor is null then 'system' else 'admin' end,
                   'market.settle', 'market', p_market::text, null, to_jsonb(st),
                   case when p_actor is null then null else 'manual settlement' end);
  return st;
end $$;

-- void a market and refund every open prediction (safe to retry)
create or replace function void_market(p_market uuid, p_reason text, p_actor uuid default null)
returns settlements
language plpgsql as $$
declare
  m   markets%rowtype;
  st  settlements%rowtype;
  p   predictions%rowtype;
  rs  uuid;
  av  uuid;
  tx  uuid;
  cnt integer := 0;
begin
  if p_reason is null or length(btrim(p_reason)) = 0 then raise exception 'reason_required'; end if;

  select * into m from markets where id = p_market for update;
  if not found then raise exception 'market_not_found'; end if;

  select * into st from settlements where market_id = p_market;
  if found then return st; end if;

  for p in select * from predictions where market_id = p_market and status = 'open' order by id for update loop
    select id into rs from ledger_accounts where owner_user_id = p.user_id and account_type = 'user_reserved';
    select id into av from ledger_accounts where owner_user_id = p.user_id and account_type = 'user_available';
    tx := gen_random_uuid();
    insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo)
    values (tx, rs, -p.stake, 'refund', 'prediction', p.id, 'refund:' || p.id, 'Refund: market voided'),
           (tx, av,  p.stake, 'refund', 'prediction', p.id, 'refund:' || p.id, 'Refund: market voided');
    update predictions set status = 'refunded', payout_amount = p.stake, settled_at = now() where id = p.id;
    cnt := cnt + 1;
  end loop;

  insert into settlements(market_id, result, rule, reason, settled_by, predictions_settled)
  values (p_market, 'void', 'void => refund all stakes', p_reason, p_actor, cnt)
  returning * into st;

  update markets set status = 'voided' where id = p_market;
  perform wd_audit(p_actor, case when p_actor is null then 'system' else 'admin' end,
                   'market.void', 'market', p_market::text, null, to_jsonb(st),
                   case when p_actor is null then p_reason else p_reason end);
  return st;
end $$;

-- admin demo-credit adjustment (positive or negative), idempotent
create or replace function adjust_demo_credits(
  p_user uuid, p_amount bigint, p_key text, p_actor uuid, p_reason text
) returns bigint
language plpgsql as $$
declare
  av   uuid;
  mint uuid;
  tx   uuid := gen_random_uuid();
  bal  bigint;
begin
  if p_amount = 0 then raise exception 'amount_zero'; end if;
  if p_reason is null or length(btrim(p_reason)) = 0 then raise exception 'reason_required'; end if;
  if p_actor is null then raise exception 'actor_required'; end if;

  select id into av from ledger_accounts where owner_user_id = p_user and account_type = 'user_available';
  if av is null then raise exception 'user_not_found'; end if;
  select id into mint from ledger_accounts where account_type = 'system_mint' and owner_user_id is null;

  if exists (select 1 from ledger_entries where idempotency_key = 'adj:' || p_key and account_id = av) then
    select balance into bal from ledger_accounts where id = av;
    return bal;
  end if;

  begin
    insert into ledger_entries(tx_id, account_id, amount, kind, ref_type, ref_id, idempotency_key, memo) values
      (tx, mint, -p_amount, 'admin_adjustment', 'user', p_user, 'adj:' || p_key, p_reason),
      (tx, av,    p_amount, 'admin_adjustment', 'user', p_user, 'adj:' || p_key, p_reason);
  exception when check_violation then
    raise exception 'insufficient_balance';
  end;

  perform wd_audit(p_actor, 'admin', 'wallet.adjust', 'user', p_user::text, null,
                   jsonb_build_object('amount', p_amount, 'key', p_key), p_reason);
  select balance into bal from ledger_accounts where id = av;
  return bal;
end $$;

-- betting window passed => status 'closed' (called by the worker)
create or replace function close_due_markets() returns integer
language plpgsql as $$
declare n integer;
begin
  with c as (
    update markets set status = 'closed'
    where status in ('open','paused') and now() >= betting_closes_at
    returning 1
  ) select count(*) into n from c;
  return n;
end $$;

-- ---------------------------------------------------------------------
-- reconciliation: returns rows ONLY when something is wrong
-- ---------------------------------------------------------------------
create or replace function ledger_reconcile()
returns table(check_name text, detail text)
language sql stable as $$
  select 'balance_cache_mismatch', a.id::text || ' cached=' || a.balance || ' ledger=' || coalesce(s.total, 0)
  from ledger_accounts a
  left join (select account_id, sum(amount) total from ledger_entries group by account_id) s on s.account_id = a.id
  where a.balance <> coalesce(s.total, 0)
  union all
  select 'unbalanced_tx', tx_id::text || ' sum=' || sum(amount)
  from ledger_entries group by tx_id having sum(amount) <> 0
  union all
  select 'system_total_nonzero', 'sum=' || sum(amount) from ledger_entries having coalesce(sum(amount), 0) <> 0
  union all
  select 'reserved_vs_open_stakes', r.owner_user_id::text || ' reserved=' || r.balance || ' open=' || coalesce(o.total, 0)
  from ledger_accounts r
  left join (select user_id, sum(stake) total from predictions where status = 'open' group by user_id) o on o.user_id = r.owner_user_id
  where r.account_type = 'user_reserved' and r.balance <> coalesce(o.total, 0)
$$;

-- ---------------------------------------------------------------------
-- views (wallet + leaderboard inputs)
-- ---------------------------------------------------------------------
create view v_wallet as
select u.id as user_id,
       av.balance as available,
       rs.balance as reserved,
       av.balance + rs.balance as total
from users u
join ledger_accounts av on av.owner_user_id = u.id and av.account_type = 'user_available'
join ledger_accounts rs on rs.owner_user_id = u.id and rs.account_type = 'user_reserved';

create view v_user_stats as
select u.id as user_id,
       count(p.id) filter (where p.status in ('won','lost'))              as settled_count,
       count(p.id) filter (where p.status = 'won')                        as wins,
       coalesce(sum(p.stake) filter (where p.status in ('open','won','lost')), 0) as total_staked,
       coalesce(sum(p.payout_amount) filter (where p.status = 'won'), 0)  as total_won,
       case when count(p.id) filter (where p.status in ('won','lost')) = 0 then null
            else round(100.0 * count(p.id) filter (where p.status = 'won')
                       / count(p.id) filter (where p.status in ('won','lost')), 2) end as accuracy_pct
from users u
left join predictions p on p.user_id = u.id
group by u.id;

-- ---------------------------------------------------------------------
-- seed data (no prices, no markets — those must come from real providers/admin)
-- ---------------------------------------------------------------------
insert into assets(symbol, name, decimals, is_prediction_asset, provider_key) values
  ('SOL',    'Solana', 9, true,  null),
  ('WIENER', 'Wiener', 6, true,  null),
  ('USDC',   'USD Coin', 6, false, null);

insert into vip_tiers(name, min_staked, reward, sort_order, benefits) values
  ('Bronze',     500000000,  5000000, 1, '["Bronze badge"]'),
  ('Silver',    2000000000, 20000000, 2, '["Silver badge"]'),
  ('Gold',      5000000000, 50000000, 3, '["Gold badge"]'),
  ('Platinum', 10000000000,100000000, 4, '["Platinum badge"]');

insert into application_settings(key, value, description) values
  ('wallet.signup_grant',                 '1000000000', 'DEMO credits granted on signup (base units; 1 DEMO = 1,000,000)'),
  ('payments.enabled',                    'false',      'Hard switch for deposits/withdrawals. Keep false until legal + security review.'),
  ('markets.monthly_enabled',             'false',      'Allow 30-day markets'),
  ('price.stale_after_seconds',           '120',        'Snapshot older than this => feed stale => pause new predictions'),
  ('price.max_move_bps_per_check',        '1500',       'Abnormal movement threshold (basis points) between consecutive snapshots'),
  ('settlement.max_snapshot_delay_seconds','300',       'Settlement snapshot must be within this many seconds after close'),
  ('referral.reward',                     '5000000',    'Referral reward in base units (demo credits)'),
  ('referral.min_predictions',            '1',          'Referred user must place this many predictions before reward is eligible'),
  ('leaderboard.min_settled',             '1',          'Minimum settled predictions to appear on leaderboard');

-- ---------------------------------------------------------------------
-- access: deny-all for browser roles; backend uses its own server-side role
-- ---------------------------------------------------------------------
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;

  if current_setting('server_version_num')::int >= 150000 then
    execute 'alter view public.v_wallet set (security_invoker = true)';
    execute 'alter view public.v_user_stats set (security_invoker = true)';
  end if;

  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on all tables in schema public from anon';
    execute 'revoke all on all sequences in schema public from anon';
    execute 'revoke all on all functions in schema public from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on all tables in schema public from authenticated';
    execute 'revoke all on all sequences in schema public from authenticated';
    execute 'revoke all on all functions in schema public from authenticated';
  end if;
end $$;

commit;
