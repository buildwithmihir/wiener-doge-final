#!/usr/bin/env bash
# Concurrency + truncate checks on COMMITTED data (separate throwaway DB).
# Usage: PSQL="psql -h /tmp -p 54329 -U postgres" bash supabase/tests/concurrency_test.sh
set -u
PSQL="${PSQL:-psql -h /tmp -p 54329 -U postgres}"
DB=wd_conc
HERE="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
check() { if [ "$2" = "$3" ]; then echo "PASS $1 ($2)"; else echo "FAIL $1: got $2 wanted $3"; fail=1; fi; }

$PSQL -qc "drop database if exists $DB" -c "create database $DB" >/dev/null
$PSQL -d $DB -q -v ON_ERROR_STOP=1 -f "$HERE/migrations/0001_init_schema.sql" >/dev/null

$PSQL -d $DB -q -v ON_ERROR_STOP=1 >/dev/null <<'SQL'
insert into users(telegram_id, display_name) values (2001,'Racer');
insert into markets(asset_id, duration_seconds, target_price, opens_at, betting_closes_at, closes_at, status)
select id, 86400, 119.40, now() - interval '1 minute', now() + interval '23 hours', now() + interval '24 hours', 'open'
from assets where symbol='SOL';
SQL
U=$($PSQL -d $DB -Atc "select id from users limit 1")
M=$($PSQL -d $DB -Atc "select id from markets limit 1")

# 1) DOUBLE-SPEND: balance 1000 DEMO, 8 parallel stakes of 600 DEMO with DIFFERENT keys -> exactly 1 may succeed
for i in 1 2 3 4 5 6 7 8; do
  $PSQL -d $DB -qAt -c "select place_prediction('$U','$M','above',600000000,'race-diff-key-$i')" >/dev/null 2>&1 &
done; wait
check "double-spend: predictions created"   "$($PSQL -d $DB -Atc "select count(*) from predictions")" 1
check "double-spend: reserved"              "$($PSQL -d $DB -Atc "select reserved from v_wallet")" 600000000
check "double-spend: available"             "$($PSQL -d $DB -Atc "select available from v_wallet")" 400000000

# 2) DUPLICATE REQUESTS: 20 parallel calls, SAME key, 10 DEMO -> exactly 1 prediction, 1 reserve
for i in $(seq 1 20); do
  $PSQL -d $DB -qAt -c "select place_prediction('$U','$M','below',10000000,'same-key-0001')" >/dev/null 2>&1 &
done; wait
check "duplicate key: predictions with key" "$($PSQL -d $DB -Atc "select count(*) from predictions where idempotency_key='same-key-0001'")" 1
check "duplicate key: reserved"             "$($PSQL -d $DB -Atc "select reserved from v_wallet")" 610000000

# 3) CONCURRENT SETTLEMENT: age market, parallel settle -> one settlement, one payout
$PSQL -d $DB -q >/dev/null <<'SQL'
alter table markets disable trigger trg_markets_guard;
update markets set opens_at = now() - interval '3 days', betting_closes_at = now() - interval '2 days', closes_at = now() - interval '1 hour';
alter table markets enable trigger trg_markets_guard;
insert into market_price_snapshots(asset_id, price, source, fetched_at)
select asset_id, 125, 'test', closes_at + interval '1 minute' from markets;
SQL
S=$($PSQL -d $DB -Atc "select max(id) from market_price_snapshots")
for i in 1 2 3 4 5 6; do
  $PSQL -d $DB -qAt -c "select settle_market('$M', $S)" >/dev/null 2>&1 &
done; wait
check "concurrent settle: settlements"      "$($PSQL -d $DB -Atc "select count(*) from settlements")" 1
check "concurrent settle: available"        "$($PSQL -d $DB -Atc "select available from v_wallet")" 1470000000
check "concurrent settle: reserved"         "$($PSQL -d $DB -Atc "select reserved from v_wallet")" 0
check "reconcile rows (must be 0)"          "$($PSQL -d $DB -Atc "select count(*) from ledger_reconcile()")" 0

# 4) TRUNCATE on committed ledger must be blocked by our trigger
OUT=$($PSQL -d $DB -Atc "truncate ledger_entries" 2>&1)
case "$OUT" in *ledger_is_append_only*) echo "PASS truncate blocked";; *) echo "FAIL truncate: $OUT"; fail=1;; esac
OUT=$($PSQL -d $DB -Atc "truncate audit_logs" 2>&1)
case "$OUT" in *audit_log_is_append_only*) echo "PASS audit truncate blocked";; *) echo "FAIL audit truncate: $OUT"; fail=1;; esac

$PSQL -qc "drop database $DB" >/dev/null
[ $fail = 0 ] && echo "ALL CONCURRENCY TESTS PASSED" || { echo "SOME CONCURRENCY TESTS FAILED"; exit 1; }
