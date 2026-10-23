"""Database test for the wallet service. SAFE for a real Supabase project: everything
runs inside ONE transaction that is rolled back at the end, so nothing is saved.

Needs DATABASE_URL in backend/.env pointing at a database where the migration was applied.

Run from the backend folder (no pytest needed):
    python -m tests.test_ledger_db
"""
import os
import sys
import uuid

# Only the secret is forced; DATABASE_URL comes from the environment / backend/.env.
os.environ.setdefault("JWT_SECRET", "t" * 48)

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import NotFound, translate_db_error
from app.database import check_db, session_scope
from app.services.ledger import (
    adjust_demo_credits,
    get_wallet,
    list_transactions,
    run_reconciliation,
)

DEMO = 1_000_000


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1

    with session_scope() as db:
        # nothing below is committed: we roll back explicitly at the end
        tag = uuid.uuid4().int % 10**12
        user_id = db.execute(
            text("insert into users(telegram_id, display_name) values (:t, 'Wallet Test') returning id"),
            {"t": 9_000_000_000_000 + tag},
        ).scalar_one()
        admin_id = db.execute(
            text("insert into users(telegram_id, display_name) values (:t, 'Admin Test') returning id"),
            {"t": 9_100_000_000_000 + tag},
        ).scalar_one()

        grant = int(db.execute(text("select wd_setting_int('wallet.signup_grant', 0)")).scalar_one())
        wallet = get_wallet(db, user_id)
        assert (wallet.available, wallet.reserved, wallet.total) == (grant, 0, grant), wallet
        print("PASS signup grant visible in wallet:", wallet)

        asset_id = db.execute(text("select id from assets where symbol = 'SOL'")).scalar_one()
        market_id = db.execute(
            text(
                """insert into markets(asset_id, duration_seconds, target_price, opens_at, betting_closes_at, closes_at, status)
                   values (:a, 86400, 119.40, now() - interval '1 minute', now() + interval '23 hours', now() + interval '24 hours', 'open')
                   returning id"""
            ),
            {"a": asset_id},
        ).scalar_one()
        db.execute(
            text("select place_prediction(:u, :m, 'above', cast(:s as bigint), :k)"),
            {"u": user_id, "m": market_id, "s": 100 * DEMO, "k": "wallet-test-key-1"},
        )
        wallet = get_wallet(db, user_id)
        assert (wallet.available, wallet.reserved, wallet.total) == (grant - 100 * DEMO, 100 * DEMO, grant), wallet
        print("PASS stake moves available -> reserved, total unchanged")

        events, next_cursor = list_transactions(db, user_id)
        assert [e.kind for e in events] == ["stake_reserve", "signup_grant"], [e.kind for e in events]
        stake, signup = events
        assert (stake.available_delta, stake.reserved_delta, stake.net) == (-100 * DEMO, 100 * DEMO, 0), stake
        assert stake.title == "Stake reserved for a prediction" and stake.ref_type == "prediction"
        assert (signup.available_delta, signup.net) == (grant, grant), signup
        assert next_cursor is None
        print("PASS history rows and explanations")

        first_page, cursor = list_transactions(db, user_id, limit=1)
        assert [e.kind for e in first_page] == ["stake_reserve"] and cursor is not None
        second_page, cursor2 = list_transactions(db, user_id, limit=1, before_cursor=cursor)
        assert [e.kind for e in second_page] == ["signup_grant"] and cursor2 is None
        print("PASS pagination")

        new_balance = adjust_demo_credits(
            db, user_id=user_id, amount_units=5 * DEMO, idempotency_key="adjust-test-0001",
            actor_id=admin_id, reason="test credit",
        )
        again = adjust_demo_credits(
            db, user_id=user_id, amount_units=5 * DEMO, idempotency_key="adjust-test-0001",
            actor_id=admin_id, reason="test credit",
        )
        assert new_balance == again == get_wallet(db, user_id).available
        assert get_wallet(db, user_id).total == grant + 5 * DEMO
        events, _ = list_transactions(db, user_id, limit=1)
        assert events[0].kind == "admin_adjustment" and events[0].net == 5 * DEMO
        print("PASS admin adjustment applied once (idempotent) and shown in history")

        try:
            with db.begin_nested():  # savepoint: the expected failure must not poison the test transaction
                adjust_demo_credits(
                    db, user_id=user_id, amount_units=-10_000 * DEMO, idempotency_key="adjust-test-0002",
                    actor_id=admin_id, reason="too much",
                )
        except DBAPIError as exc:
            mapped = translate_db_error(exc)
            assert mapped is not None and mapped.code == "insufficient_balance", mapped
        else:
            raise AssertionError("overdraft was accepted")
        print("PASS overdraft rejected with friendly error code")

        try:
            get_wallet(db, uuid.uuid4())
        except NotFound:
            pass
        else:
            raise AssertionError("expected NotFound for unknown user")
        print("PASS unknown user -> NotFound")

        issues = run_reconciliation(db)
        assert issues == [], issues
        print("PASS reconciliation clean")

        db.rollback()  # discard everything this test created
    print("ALL LEDGER DB TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
