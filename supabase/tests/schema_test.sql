-- Run:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/schema_test.sql
-- Everything happens inside one transaction that is ROLLED BACK at the end.
-- Any failed expectation aborts with a message. Success prints "ALL SCHEMA TESTS PASSED".

\o /dev/null
begin;

create function pg_temp.expect_err(sql text, needle text) returns void
language plpgsql as $$
declare ok boolean := false;
begin
  begin
    execute sql;
  exception when others then
    if position(needle in sqlerrm) = 0 then
      raise exception 'WRONG ERROR for [%]: got "%", wanted "%"', sql, sqlerrm, needle;
    end if;
    ok := true;
  end;
  if not ok then
    raise exception 'EXPECTED ERROR "%" but succeeded: %', needle, sql;
  end if;
end $$;

create function pg_temp.age_market(p uuid) returns void
language plpgsql as $$
begin
  alter table markets disable trigger trg_markets_guard;   -- test-only time travel
  update markets set opens_at = now() - interval '3 days',
                     betting_closes_at = now() - interval '2 days',
                     closes_at = now() - interval '1 hour' where id = p;
  alter table markets enable trigger trg_markets_guard;
end $$;

create temp table t(k text primary key, v text);
create function pg_temp.g(p text) returns text language sql as $$ select v from t where k = p $$;
create function pg_temp.bal(u uuid, ty text) returns bigint language sql as
$$ select balance from ledger_accounts where owner_user_id = u and account_type = ty $$;

-- ---------- setup ----------
insert into users(telegram_id, display_name) values (1001,'Alice'),(1002,'Bob'),(1003,'Admin');
insert into t select 'alice', id::text from users where telegram_id = 1001;
insert into t select 'bob',   id::text from users where telegram_id = 1002;
insert into t select 'admin', id::text from users where telegram_id = 1003;
insert into user_roles(user_id, role) select id, 'admin' from users where telegram_id = 1003;
insert into t select 'sol', id::text from assets where symbol = 'SOL';
insert into referral_codes(user_id, code) select id, 'AVZ5WGNH' from users where telegram_id = 1001;

do $$
begin
  assert pg_temp.bal(pg_temp.g('alice')::uuid,'user_available') = 1000000000, 'signup grant available';
  assert pg_temp.bal(pg_temp.g('alice')::uuid,'user_reserved')  = 0,          'reserved starts 0';
  assert (select count(*) from assets where symbol='USDC' and not is_prediction_asset) = 1, 'USDC not a prediction asset';
  assert (select count(*) from ledger_reconcile()) = 0, 'reconcile clean after signup';
  raise notice 'PASS setup + signup grant + USDC separate + reconcile';
end $$;

-- ---------- market 1 ----------
insert into markets(asset_id, duration_seconds, target_price, opens_at, betting_closes_at, closes_at, status)
values (pg_temp.g('sol')::uuid, 86400, 119.40, now() - interval '1 minute', now() + interval '23 hours', now() + interval '24 hours', 'open');
insert into t select 'm1', id::text from markets order by created_at desc limit 1;

do $$
declare p1 predictions; p1b predictions; a uuid := pg_temp.g('alice')::uuid; b uuid := pg_temp.g('bob')::uuid; m uuid := pg_temp.g('m1')::uuid;
begin
  p1  := place_prediction(a, m, 'above', 100000000, 'alice-key-0001');
  assert pg_temp.bal(a,'user_available') = 900000000, 'available after stake';
  assert pg_temp.bal(a,'user_reserved')  = 100000000, 'reserved after stake';
  assert p1.potential_payout = 180000000, 'simulated payout 1.8x';

  p1b := place_prediction(a, m, 'above', 100000000, 'alice-key-0001');       -- retry same key
  assert p1b.id = p1.id, 'idempotent retry returns same prediction';
  assert pg_temp.bal(a,'user_reserved') = 100000000, 'no double reserve on retry';

  perform place_prediction(b, m, 'below', 50000000, 'bob-key-00001');
  raise notice 'PASS place prediction + idempotent retry';
end $$;

select pg_temp.expect_err($$select place_prediction(pg_temp.g('bob')::uuid, pg_temp.g('m1')::uuid, 'below', 1000000000, 'bob-key-too-big')$$, 'insufficient_balance');
select pg_temp.expect_err($$select place_prediction(pg_temp.g('bob')::uuid, pg_temp.g('m1')::uuid, 'below', 1, 'bob-key-too-small')$$, 'stake_out_of_range');
select pg_temp.expect_err($$select place_prediction(pg_temp.g('bob')::uuid, pg_temp.g('m1')::uuid, 'sideways', 5000000, 'bob-key-bad-dir')$$, 'violates check');
select pg_temp.expect_err($$update markets set target_price = 100 where id = pg_temp.g('m1')::uuid$$, 'market_terms_immutable_after_draft');
select pg_temp.expect_err($$update markets set status = 'draft' where id = pg_temp.g('m1')::uuid$$, 'illegal_market_transition');
select pg_temp.expect_err($$update ledger_entries set amount = amount + 1$$, 'ledger_is_append_only');
select pg_temp.expect_err($$delete from ledger_entries$$, 'ledger_is_append_only');
select pg_temp.expect_err($$update ledger_accounts set balance = 999999999999 where account_type = 'user_available'$$, 'balance_is_ledger_managed');
select pg_temp.expect_err($$update predictions set stake = 1$$, 'prediction_terms_immutable');
select pg_temp.expect_err($$delete from predictions$$, 'predictions_are_permanent');
select pg_temp.expect_err($$update audit_logs set action = 'x'$$, 'audit_log_is_append_only');
select pg_temp.expect_err($$select wd_audit(null,'admin','x','y','1',null,null,'')$$, 'violates check');
select pg_temp.expect_err($$insert into deposits(user_id,asset_id,amount,chain,external_tx_ref) select u.id, a.id, 1, 'solana', 'sig1' from users u, assets a limit 1$$, 'payments_disabled_demo_only');
select pg_temp.expect_err($$insert into referrals(referrer_id, referred_id, code_id) select user_id, user_id, id from referral_codes where code = 'AVZ5WGNH'$$, 'referrals_check');
select pg_temp.expect_err($$insert into referral_codes(user_id, code) select id, 'AVZ5WGNH' from users where telegram_id = 1002$$, 'referral_codes_code_key');

-- unbalanced ledger tx must fail at commit-time constraint
do $$
declare av uuid;
begin
  select id into av from ledger_accounts where account_type='user_available' limit 1;
  insert into ledger_entries(tx_id, account_id, amount, kind, idempotency_key)
  values (gen_random_uuid(), av, 5, 'admin_adjustment', 'bad-unbalanced');
  begin
    set constraints trg_ledger_tx_balanced immediate;
    raise exception 'unbalanced tx was ACCEPTED';
  exception when others then
    if position('ledger_tx_unbalanced' in sqlerrm) = 0 then raise; end if;
  end;
  raise notice 'PASS append-only ledger, immutability, payments disabled, unbalanced tx rejected';
end $$;
-- (the failed statement above left an unbalanced row in this tx; undo it)
rollback;

-- re-run setup for the settlement section (fresh transaction)
begin;
create function pg_temp.age_market(p uuid) returns void
language plpgsql as $$
begin
  alter table markets disable trigger trg_markets_guard;
  update markets set opens_at = now() - interval '3 days',
                     betting_closes_at = now() - interval '2 days',
                     closes_at = now() - interval '1 hour' where id = p;
  alter table markets enable trigger trg_markets_guard;
end $$;
create function pg_temp.expect_err(sql text, needle text) returns void
language plpgsql as $$
declare ok boolean := false;
begin
  begin execute sql;
  exception when others then
    if position(needle in sqlerrm) = 0 then
      raise exception 'WRONG ERROR for [%]: got "%", wanted "%"', sql, sqlerrm, needle;
    end if;
    ok := true;
  end;
  if not ok then raise exception 'EXPECTED ERROR "%" but succeeded: %', needle, sql; end if;
end $$;
create temp table t(k text primary key, v text);
create function pg_temp.g(p text) returns text language sql as $$ select v from t where k = p $$;
create function pg_temp.bal(u uuid, ty text) returns bigint language sql as
$$ select balance from ledger_accounts where owner_user_id = u and account_type = ty $$;

insert into users(telegram_id, display_name) values (1001,'Alice'),(1002,'Bob'),(1003,'Admin');
insert into t select 'alice', id::text from users where telegram_id = 1001;
insert into t select 'bob',   id::text from users where telegram_id = 1002;
insert into t select 'admin', id::text from users where telegram_id = 1003;
insert into t select 'sol', id::text from assets where symbol = 'SOL';

insert into markets(asset_id, duration_seconds, target_price, opens_at, betting_closes_at, closes_at, status)
values (pg_temp.g('sol')::uuid, 86400, 119.40, now() - interval '1 minute', now() + interval '23 hours', now() + interval '24 hours', 'open');
insert into t select 'm1', id::text from markets order by created_at desc limit 1;

do $$
declare a uuid := pg_temp.g('alice')::uuid; b uuid := pg_temp.g('bob')::uuid; m uuid := pg_temp.g('m1')::uuid;
begin
  perform place_prediction(a, m, 'above', 100000000, 'alice-key-0001');
  perform place_prediction(b, m, 'below',  50000000, 'bob-key-00001');
end $$;

-- pause blocks new predictions, reopen works
update markets set status = 'paused', pause_reason = 'feed unhealthy' where id = pg_temp.g('m1')::uuid;
select pg_temp.expect_err($$select place_prediction(pg_temp.g('bob')::uuid, pg_temp.g('m1')::uuid, 'above', 5000000, 'bob-key-paused')$$, 'market_not_open');
update markets set status = 'open', pause_reason = null where id = pg_temp.g('m1')::uuid;

-- settlement guards
insert into market_price_snapshots(asset_id, price, source, fetched_at)
values (pg_temp.g('sol')::uuid, 119.40, 'test', now());
insert into t select 'snap_early', max(id)::text from market_price_snapshots;
select pg_temp.expect_err($$select settle_market(pg_temp.g('m1')::uuid, pg_temp.g('snap_early')::bigint)$$, 'market_not_closed_yet');

select pg_temp.age_market(pg_temp.g('m1')::uuid);
select close_due_markets();
do $$ begin assert (select status from markets where id = pg_temp.g('m1')::uuid) = 'closed', 'worker closed market'; end $$;
select pg_temp.expect_err($$select place_prediction(pg_temp.g('bob')::uuid, pg_temp.g('m1')::uuid, 'above', 5000000, 'bob-key-late')$$, 'market_not_open');

-- bad snapshots: stale, too early (before close), too late (outside window)
insert into market_price_snapshots(asset_id, price, source, fetched_at, is_stale)
select pg_temp.g('sol')::uuid, 120, 'test-stale', closes_at + interval '1 minute', true from markets where id = pg_temp.g('m1')::uuid;
insert into t select 'snap_stale', max(id)::text from market_price_snapshots;
insert into market_price_snapshots(asset_id, price, source, fetched_at)
select pg_temp.g('sol')::uuid, 120, 'test-early', closes_at - interval '5 minutes' from markets where id = pg_temp.g('m1')::uuid;
insert into t select 'snap_before', max(id)::text from market_price_snapshots;
insert into market_price_snapshots(asset_id, price, source, fetched_at)
select pg_temp.g('sol')::uuid, 120, 'test-late', closes_at + interval '1 day' from markets where id = pg_temp.g('m1')::uuid;
insert into t select 'snap_late', max(id)::text from market_price_snapshots;
select pg_temp.expect_err($$select settle_market(pg_temp.g('m1')::uuid, pg_temp.g('snap_stale')::bigint)$$, 'snapshot_unreliable');
select pg_temp.expect_err($$select settle_market(pg_temp.g('m1')::uuid, pg_temp.g('snap_before')::bigint)$$, 'snapshot_outside_settlement_window');
select pg_temp.expect_err($$select settle_market(pg_temp.g('m1')::uuid, pg_temp.g('snap_late')::bigint)$$, 'snapshot_outside_settlement_window');
select pg_temp.expect_err($$select settle_market(pg_temp.g('m1')::uuid, 999999)$$, 'price_unavailable');

-- good snapshot EXACTLY at target => tie goes to ABOVE
insert into market_price_snapshots(asset_id, price, source, fetched_at)
select pg_temp.g('sol')::uuid, 119.40, 'test-good', closes_at + interval '1 minute' from markets where id = pg_temp.g('m1')::uuid;
insert into t select 'snap_good', max(id)::text from market_price_snapshots;

do $$
declare a uuid := pg_temp.g('alice')::uuid; b uuid := pg_temp.g('bob')::uuid; m uuid := pg_temp.g('m1')::uuid;
        s1 settlements; s2 settlements; house bigint;
begin
  s1 := settle_market(m, pg_temp.g('snap_good')::bigint);
  assert s1.result = 'above', 'tie (price = target) resolves ABOVE';
  assert pg_temp.bal(a,'user_available') = 1080000000, 'alice paid 1.8x';
  assert pg_temp.bal(a,'user_reserved')  = 0, 'alice reserve released';
  assert pg_temp.bal(b,'user_available') = 950000000, 'bob lost 50';
  assert pg_temp.bal(b,'user_reserved')  = 0, 'bob reserve released';
  select balance into house from ledger_accounts where account_type = 'system_house';
  assert house = -30000000, 'house = +50 -80 = -30';

  s2 := settle_market(m, pg_temp.g('snap_good')::bigint);   -- retry
  assert s2.id = s1.id, 'settlement retry idempotent';
  assert pg_temp.bal(a,'user_available') = 1080000000, 'no double payout on retry';
  assert (select count(*) from ledger_reconcile()) = 0, 'reconcile clean after settlement';
  assert (select accuracy_pct from v_user_stats where user_id = a) = 100.00, 'alice accuracy 100';
  assert (select accuracy_pct from v_user_stats where user_id = b) = 0.00,   'bob accuracy 0';
  raise notice 'PASS paused/closed blocks, snapshot guards, tie rule, payouts, retry-safe, reconcile';
end $$;

select pg_temp.expect_err($$update markets set status = 'open' where id = pg_temp.g('m1')::uuid$$, 'market_final_state_immutable');

-- void + refunds
insert into markets(asset_id, duration_seconds, target_price, opens_at, betting_closes_at, closes_at, status)
values (pg_temp.g('sol')::uuid, 172800, 120, now() - interval '1 minute', now() + interval '47 hours', now() + interval '48 hours', 'open');
insert into t select 'm2', id::text from markets where target_price = 120;
do $$
declare a uuid := pg_temp.g('alice')::uuid; b uuid := pg_temp.g('bob')::uuid; m uuid := pg_temp.g('m2')::uuid;
        v1 settlements; v2 settlements; abefore bigint; bbefore bigint;
begin
  abefore := pg_temp.bal(a,'user_available'); bbefore := pg_temp.bal(b,'user_available');
  perform place_prediction(a, m, 'below', 10000000, 'alice-key-0002');
  perform place_prediction(b, m, 'above', 20000000, 'bob-key-00002');
  assert pg_temp.bal(a,'user_available') = abefore - 10000000, 'alice stake reserved';
  begin perform void_market(m, '   ', null); raise exception 'void without reason accepted';
  exception when others then if position('reason_required' in sqlerrm) = 0 then raise; end if; end;
  v1 := void_market(m, 'price feed unreliable', pg_temp.g('admin')::uuid);
  v2 := void_market(m, 'price feed unreliable', pg_temp.g('admin')::uuid);
  assert v1.id = v2.id and v1.result = 'void', 'void idempotent';
  assert pg_temp.bal(a,'user_available') = abefore, 'alice refunded in full';
  assert pg_temp.bal(b,'user_available') = bbefore, 'bob refunded in full';
  assert (select count(*) from predictions where market_id = m and status = 'refunded') = 2, 'both refunded';
  assert (select count(*) from ledger_reconcile()) = 0, 'reconcile clean after void';
  raise notice 'PASS void + refund + idempotency';
end $$;

-- admin adjustments
do $$
declare ad uuid := pg_temp.g('admin')::uuid; a uuid := pg_temp.g('alice')::uuid; before_bal bigint; r bigint;
begin
  before_bal := pg_temp.bal(a,'user_available');
  r := adjust_demo_credits(a, 5000000, 'adj-test-0001', ad, 'goodwill');
  r := adjust_demo_credits(a, 5000000, 'adj-test-0001', ad, 'goodwill');   -- retry
  assert pg_temp.bal(a,'user_available') = before_bal + 5000000, 'adjustment applied once';
  begin perform adjust_demo_credits(a, -99999999999, 'adj-test-0002', ad, 'too much');
        raise exception 'overdraft accepted';
  exception when others then if position('insufficient_balance' in sqlerrm) = 0 then raise; end if; end;
  begin perform adjust_demo_credits(a, 1, 'adj-test-0003', ad, '');
        raise exception 'adjust without reason accepted';
  exception when others then if position('reason_required' in sqlerrm) = 0 then raise; end if; end;
  assert (select count(*) from audit_logs where action = 'wallet.adjust' and reason = 'goodwill') = 1, 'audit row for adjustment';
  assert (select count(*) from ledger_reconcile()) = 0, 'reconcile clean after adjustments';
  raise notice 'PASS admin adjustment (reason, audit, idempotent, no overdraft)';
end $$;

rollback;

\o
\echo
\echo ALL SCHEMA TESTS PASSED
